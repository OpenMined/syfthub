package containermode

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// terminalEvents are event types that signal the end of an agent session.
var terminalEvents = map[string]bool{
	"agent.session_complete": true,
	"agent.session_failed":   true,
	"session.completed":      true,
	"session.failed":         true,
}

// NewContainerAgentHandler returns an AgentHandler that bridges a Go AgentSession
// to a container's HTTP session API using SSE for server-push and POST for client-push.
func NewContainerAgentHandler(executor *ContainerExecutor, logger *slog.Logger) syfthubapi.AgentHandler {
	return func(ctx context.Context, session *syfthubapi.AgentSession) error {
		baseURL := executor.BaseURL()

		// 1. Start session in container
		startPayload := map[string]any{
			"session_id": session.ID,
			"prompt":     session.InitialPrompt,
			"messages":   session.Messages,
			"config":     session.Config,
		}
		body, err := json.Marshal(startPayload)
		if err != nil {
			return fmt.Errorf("failed to marshal session start: %w", err)
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/session/start", bytes.NewReader(body))
		if err != nil {
			return fmt.Errorf("failed to create session start request: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")

		client := &http.Client{Timeout: 10 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			return fmt.Errorf("failed to start session in container: %w", err)
		}
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("container returned %d for session start", resp.StatusCode)
		}

		logger.Info("[CONTAINER-AGENT] session started in container",
			"session_id", session.ID,
			"base_url", baseURL,
		)

		// 2. Spawn reader and writer goroutines
		readerCtx, readerCancel := context.WithCancel(ctx)
		defer readerCancel()

		writerCtx, writerCancel := context.WithCancel(ctx)
		defer writerCancel()

		readerDone := make(chan error, 1)
		go func() {
			readerDone <- readSSEEvents(readerCtx, baseURL, session.ID, session, logger)
		}()

		writerDone := make(chan struct{})
		go func() {
			defer close(writerDone)
			writeUserMessages(writerCtx, baseURL, session.ID, session, logger)
		}()

		// 3. Wait for reader to complete (signals session end)
		readerErr := <-readerDone

		// 4. Cancel writer
		writerCancel()
		select {
		case <-writerDone:
		case <-time.After(5 * time.Second):
			logger.Warn("[CONTAINER-AGENT] writer did not stop in time", "session_id", session.ID)
		}

		// 5. Clean up session in container (best-effort)
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		deleteReq, _ := http.NewRequestWithContext(cleanupCtx, http.MethodDelete,
			fmt.Sprintf("%s/session/%s", baseURL, session.ID), nil)
		if deleteReq != nil {
			if resp, err := client.Do(deleteReq); err == nil {
				resp.Body.Close()
			}
		}

		return readerErr
	}
}

// readSSEEvents reads SSE events from the container with retry support.
func readSSEEvents(ctx context.Context, baseURL, sessionID string, session *syfthubapi.AgentSession, logger *slog.Logger) error {
	maxRetries := 3
	lastEventID := ""

	for attempt := 0; attempt < maxRetries; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Second):
			}
			logger.Info("[CONTAINER-AGENT] SSE reconnecting",
				"session_id", sessionID,
				"attempt", attempt+1,
				"last_event_id", lastEventID,
			)
		}

		newLastID, err := streamSSEEvents(ctx, baseURL, sessionID, lastEventID, session, logger)
		if newLastID != "" {
			lastEventID = newLastID
		}

		if err == nil {
			// Clean exit (terminal event received)
			return nil
		}

		if ctx.Err() != nil {
			return ctx.Err()
		}

		logger.Warn("[CONTAINER-AGENT] SSE stream error, will retry",
			"session_id", sessionID,
			"error", err,
		)
	}

	return fmt.Errorf("SSE reader exhausted %d retries", maxRetries)
}

// streamSSEEvents opens a single SSE connection and streams events.
// Returns the last event ID seen and nil on clean terminal event, or an error.
func streamSSEEvents(ctx context.Context, baseURL, sessionID, lastEventID string, session *syfthubapi.AgentSession, logger *slog.Logger) (string, error) {
	url := fmt.Sprintf("%s/session/%s/events", baseURL, sessionID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return lastEventID, err
	}
	req.Header.Set("Accept", "text/event-stream")
	if lastEventID != "" {
		req.Header.Set("Last-Event-ID", lastEventID)
	}

	client := &http.Client{} // No timeout — SSE is long-lived
	resp, err := client.Do(req)
	if err != nil {
		return lastEventID, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return lastEventID, fmt.Errorf("SSE returned status %d", resp.StatusCode)
	}

	err = parseSSEStream(resp.Body, func(eventType, data, id string) {
		if id != "" {
			lastEventID = id
		}

		event := syfthubapi.AgentEventPayload{
			EventType: eventType,
			Data:      json.RawMessage(data),
		}
		if sendErr := session.Send(event); sendErr != nil {
			logger.Warn("[CONTAINER-AGENT] failed to send event",
				"session_id", sessionID,
				"event_type", eventType,
				"error", sendErr,
			)
		}

		if terminalEvents[eventType] {
			logger.Info("[CONTAINER-AGENT] terminal event received",
				"session_id", sessionID,
				"event_type", eventType,
			)
		}
	})

	return lastEventID, err
}

// parseSSEStream parses a Server-Sent Events stream according to the SSE spec.
// It calls the callback for each complete event (dispatched on blank line).
func parseSSEStream(reader io.Reader, callback func(eventType, data, id string)) error {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024) // 1MB max line

	var eventType string
	var dataLines []string
	var id string

	for scanner.Scan() {
		line := scanner.Text()

		if line == "" {
			// Blank line: dispatch event
			if len(dataLines) > 0 {
				data := strings.Join(dataLines, "\n")
				if eventType == "" {
					eventType = "message"
				}
				callback(eventType, data, id)

				// Check for terminal event to allow early exit
				if terminalEvents[eventType] {
					return nil
				}
			}
			eventType = ""
			dataLines = nil
			id = ""
			continue
		}

		if strings.HasPrefix(line, ":") {
			// Comment line, skip
			continue
		}

		field, value, _ := strings.Cut(line, ":")
		value = strings.TrimPrefix(value, " ") // SSE spec: remove single leading space

		switch field {
		case "event":
			eventType = value
		case "data":
			dataLines = append(dataLines, value)
		case "id":
			id = value
		}
	}

	return scanner.Err()
}

// writeUserMessages forwards user messages from the session to the container.
func writeUserMessages(ctx context.Context, baseURL, sessionID string, session *syfthubapi.AgentSession, logger *slog.Logger) {
	client := &http.Client{Timeout: 10 * time.Second}
	url := fmt.Sprintf("%s/session/%s/message", baseURL, sessionID)

	for {
		msg, err := session.Receive()
		if err != nil {
			// Context cancelled or session done
			return
		}

		body, err := json.Marshal(msg)
		if err != nil {
			logger.Warn("[CONTAINER-AGENT] failed to marshal message", "session_id", sessionID, "error", err)
			continue
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
		if err != nil {
			return
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			logger.Warn("[CONTAINER-AGENT] failed to deliver message", "session_id", sessionID, "error", err)
			continue
		}
		resp.Body.Close()
	}
}
