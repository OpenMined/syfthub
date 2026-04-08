package syfthub

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/coder/websocket"
	"github.com/openmined/syfthub/sdk/golang/agenttypes"
)

// AgentSessionConfig is an alias for the shared agent config type.
// Kept for backward compatibility so callers can continue using syfthub.AgentSessionConfig.
type AgentSessionConfig = agenttypes.AgentConfig

// AgentMessage is an alias for the shared message type.
// Kept for backward compatibility so callers can continue using syfthub.AgentMessage.
type AgentMessage = agenttypes.Message

// AgentResource provides agent session functionality via the Aggregator.
//
// Example usage:
//
//	session, err := client.Agent().StartSession(ctx, &AgentSessionRequest{
//	    Prompt:   "Help me refactor this code",
//	    Endpoint: "alice/code-assistant",
//	})
//	defer session.Close()
//
//	for event := range session.Events() {
//	    switch e := event.(type) {
//	    case *AgentMessageEvent:
//	        fmt.Println(e.Content)
//	    case *AgentToolCallEvent:
//	        session.Confirm(ctx, e.ToolCallID)
//	    }
//	}
type AgentResource struct {
	hub           *HubResource
	auth          *AuthResource
	aggregatorURL string
}

// newAgentResource creates a new AgentResource.
func newAgentResource(hub *HubResource, auth *AuthResource, aggregatorURL string) *AgentResource {
	return &AgentResource{
		hub:           hub,
		auth:          auth,
		aggregatorURL: strings.TrimRight(aggregatorURL, "/"),
	}
}

// AgentSessionRequest contains parameters for starting an agent session.
type AgentSessionRequest struct {
	// Prompt is the initial user prompt.
	Prompt string

	// Endpoint is the agent endpoint path ("owner/slug" format).
	Endpoint string

	// Config contains optional agent configuration.
	Config *AgentSessionConfig

	// Messages contains optional conversation history.
	Messages []AgentMessage

	// AggregatorURL overrides the default aggregator URL.
	AggregatorURL string
}

// StartSession starts a new agent session.
// It resolves the endpoint, fetches tokens, opens a WebSocket connection,
// sends session.start, waits for session.created, and returns an AgentSessionClient.
func (a *AgentResource) StartSession(ctx context.Context, req *AgentSessionRequest) (*AgentSessionClient, error) {
	// Parse "owner/slug" from endpoint
	parts := strings.SplitN(req.Endpoint, "/", 2)
	if len(parts) != 2 {
		return nil, fmt.Errorf("endpoint must be in 'owner/slug' format, got: %s", req.Endpoint)
	}
	owner, slug := parts[0], parts[1]

	// Get satellite token
	satResp, err := a.auth.GetSatelliteToken(ctx, owner)
	if err != nil {
		return nil, fmt.Errorf("failed to get satellite token: %w", err)
	}

	// Get peer token for tunneling
	peerResp, err := a.auth.GetPeerToken(ctx, []string{owner})
	if err != nil {
		return nil, fmt.Errorf("failed to get peer token: %w", err)
	}

	// Build WebSocket URL
	aggregatorURL := a.aggregatorURL
	if req.AggregatorURL != "" {
		aggregatorURL = strings.TrimRight(req.AggregatorURL, "/")
	}
	wsURL := strings.Replace(aggregatorURL, "https://", "wss://", 1)
	wsURL = strings.Replace(wsURL, "http://", "ws://", 1)
	wsURL += "/agent/session"

	// Dial WebSocket
	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to agent WebSocket: %w", err)
	}

	// Build session.start message
	startPayload := map[string]any{
		"prompt": req.Prompt,
		"endpoint": map[string]string{
			"owner": owner,
			"slug":  slug,
		},
		"satellite_token": satResp.TargetToken,
		"peer_token":      peerResp.PeerToken,
		"peer_channel":    peerResp.PeerChannel,
	}
	if req.Config != nil {
		startPayload["config"] = req.Config
	}
	if len(req.Messages) > 0 {
		startPayload["messages"] = req.Messages
	}

	startMsg := map[string]any{
		"type":    "session.start",
		"payload": startPayload,
	}

	startBytes, err := json.Marshal(startMsg)
	if err != nil {
		conn.Close(websocket.StatusInternalError, "marshal error")
		return nil, fmt.Errorf("failed to marshal session.start: %w", err)
	}

	// Send session.start
	if err := conn.Write(ctx, websocket.MessageText, startBytes); err != nil {
		conn.Close(websocket.StatusInternalError, "write error")
		return nil, fmt.Errorf("failed to send session.start: %w", err)
	}

	// Read session.created response
	_, respBytes, err := conn.Read(ctx)
	if err != nil {
		conn.Close(websocket.StatusInternalError, "read error")
		return nil, fmt.Errorf("failed to read session.created: %w", err)
	}

	var resp struct {
		Type      string `json:"type"`
		SessionID string `json:"session_id"`
		Payload   struct {
			SessionID string `json:"session_id"`
			Code      string `json:"code"`
			Message   string `json:"message"`
		} `json:"payload"`
	}
	if err := json.Unmarshal(respBytes, &resp); err != nil {
		conn.Close(websocket.StatusInternalError, "unmarshal error")
		return nil, fmt.Errorf("failed to parse session.created: %w", err)
	}

	if resp.Type == "agent.error" {
		conn.Close(websocket.StatusNormalClosure, "error")
		return nil, fmt.Errorf("agent session error: [%s] %s", resp.Payload.Code, resp.Payload.Message)
	}

	sessionID := resp.SessionID
	if sessionID == "" {
		sessionID = resp.Payload.SessionID
	}

	return newAgentSessionClient(conn, sessionID), nil
}
