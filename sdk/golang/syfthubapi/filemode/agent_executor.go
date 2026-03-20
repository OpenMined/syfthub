package filemode

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"sync"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// AgentHandlerConfig holds configuration for creating a file-based agent handler.
type AgentHandlerConfig struct {
	PythonPath string
	RunnerPath string
	WorkDir    string
	Env        []string
	Logger     *slog.Logger
}

// agentWrapperScript is the Python script that bridges stdin/stdout JSON-lines
// protocol to the user's runner.py handler(session) function.
const agentWrapperScript = `
import sys
import json
import threading
import importlib.util
import traceback


class AgentSession:
    """Bidirectional agent session communicating via stdin/stdout JSON-lines."""

    def __init__(self, data):
        self.id = data.get("session_id", "")
        self.prompt = data.get("prompt", "")
        self.messages = data.get("messages", [])
        self.config = data.get("config", {})
        self._write_lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._tc_counter = 0

    def send_message(self, content):
        """Send a complete message to the user."""
        self._emit("agent.message", {"content": content, "is_complete": True})

    def send_thinking(self, content):
        """Send thinking/reasoning content."""
        self._emit("agent.thinking", {"content": content, "is_streaming": False})

    def send_status(self, status, detail=""):
        """Send a status update."""
        self._emit("agent.status", {"status": status, "detail": detail})

    def send_tool_call(self, tool_name, arguments, tool_call_id=None,
                       description="", requires_confirmation=False):
        """Send a tool call event."""
        if tool_call_id is None:
            self._tc_counter += 1
            tool_call_id = f"tc-{self._tc_counter}"
        self._emit("agent.tool_call", {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "description": description,
            "requires_confirmation": requires_confirmation,
        })

    def send_tool_result(self, tool_call_id, status="success",
                         result=None, error=None, duration_ms=0):
        """Send a tool result event."""
        self._emit("agent.tool_result", {
            "tool_call_id": tool_call_id,
            "status": status,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
        })

    def send_token(self, token):
        """Send a streaming token."""
        self._emit("agent.token", {"token": token})

    def receive(self):
        """Block until a user message arrives. Returns dict with 'type' and 'content'."""
        with self._read_lock:
            line = sys.stdin.readline()
            if not line:
                raise EOFError("Connection closed")
            msg = json.loads(line)
            if msg.get("type") == "cancel":
                raise KeyboardInterrupt("Session cancelled by user")
            return msg.get("message", {})

    def request_input(self, prompt):
        """Ask the user for input and wait for their response."""
        self._emit("agent.request_input", {"prompt": prompt})
        return self.receive()

    def request_confirmation(self, action, arguments=None, description=""):
        """Ask user to confirm an action. Returns True if confirmed."""
        self.send_tool_call(
            tool_name=action,
            arguments=arguments or {},
            description=description,
            requires_confirmation=True,
        )
        response = self.receive()
        return response.get("type") == "user_confirm"

    def _emit(self, event_type, data):
        with self._write_lock:
            sys.stdout.write(json.dumps({"type": event_type, "data": data}) + "\n")
            sys.stdout.flush()


def main():
    line = sys.stdin.readline()
    if not line:
        sys.exit(1)

    data = json.loads(line)
    session = AgentSession(data)

    spec = importlib.util.spec_from_file_location("runner", "runner.py")
    runner = importlib.util.module_from_spec(spec)
    sys.modules["runner"] = runner
    spec.loader.exec_module(runner)

    if not hasattr(runner, "handler"):
        print("runner.py must define a 'handler' function", file=sys.stderr)
        sys.exit(1)

    try:
        runner.handler(session)
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
`

// NewAgentHandler creates an AgentHandler that delegates to a Python runner.py subprocess.
// Each session spawns a new long-lived Python subprocess with JSON-lines bidirectional protocol.
func NewAgentHandler(cfg *AgentHandlerConfig) syfthubapi.AgentHandler {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return func(ctx context.Context, session *syfthubapi.AgentSession) error {
		cmd := exec.CommandContext(ctx, cfg.PythonPath, "-c", agentWrapperScript)
		cmd.Dir = cfg.WorkDir
		cmd.Env = append(os.Environ(), cfg.Env...)

		// Hide console window on Windows
		hideWindow(cmd)

		stdin, err := cmd.StdinPipe()
		if err != nil {
			return fmt.Errorf("failed to create stdin pipe: %w", err)
		}

		stdout, err := cmd.StdoutPipe()
		if err != nil {
			return fmt.Errorf("failed to create stdout pipe: %w", err)
		}

		var stderrBuf bytes.Buffer
		cmd.Stderr = &stderrBuf

		logger.Info("[AGENT-BRIDGE] Starting Python agent subprocess",
			"session_id", session.ID,
			"python", cfg.PythonPath,
			"runner", cfg.RunnerPath,
			"workdir", cfg.WorkDir,
		)

		if err := cmd.Start(); err != nil {
			return fmt.Errorf("failed to start agent subprocess: %w", err)
		}

		// Write session_start to stdin (before spawning goroutines)
		startPayload := map[string]any{
			"type":       "session_start",
			"session_id": session.ID,
			"prompt":     session.InitialPrompt,
			"messages":   session.Messages,
			"config":     session.Config,
		}
		if err := json.NewEncoder(stdin).Encode(startPayload); err != nil {
			cmd.Process.Kill()
			return fmt.Errorf("failed to write session_start: %w", err)
		}

		var wg sync.WaitGroup

		// Reader goroutine: Python stdout → session.Send()
		wg.Add(1)
		go func() {
			defer wg.Done()
			scanner := bufio.NewScanner(stdout)
			scanner.Buffer(make([]byte, 1024*1024), 1024*1024) // 1MB max line

			for scanner.Scan() {
				var envelope struct {
					Type string          `json:"type"`
					Data json.RawMessage `json:"data"`
				}
				if err := json.Unmarshal(scanner.Bytes(), &envelope); err != nil {
					logger.Warn("[AGENT-BRIDGE] Failed to parse event",
						"session_id", session.ID,
						"error", err,
					)
					continue
				}

				event := syfthubapi.AgentEventPayload{
					EventType: envelope.Type,
					Data:      envelope.Data,
				}

				if err := session.Send(event); err != nil {
					logger.Debug("[AGENT-BRIDGE] Send failed (session closing)",
						"session_id", session.ID,
						"event_type", envelope.Type,
					)
					return
				}
			}
		}()

		// Writer goroutine: session.Receive() → Python stdin
		stdinEncoder := json.NewEncoder(stdin)
		go func() {
			for {
				msg, err := session.Receive()
				if err != nil {
					return // Context cancelled or session closing
				}

				wrapper := map[string]any{
					"type":    "user_message",
					"message": msg,
				}
				if err := stdinEncoder.Encode(wrapper); err != nil {
					return // stdin closed, Python exited
				}
			}
		}()

		// Wait for Python process to exit
		waitErr := cmd.Wait()

		// Wait for reader to finish processing all buffered events
		wg.Wait()

		// Cancel session to unblock the writer goroutine
		session.Cancel()

		// Close stdin
		stdin.Close()

		if waitErr != nil {
			stderrStr := stderrBuf.String()
			if stderrStr != "" {
				logger.Error("[AGENT-BRIDGE] Python agent failed",
					"session_id", session.ID,
					"stderr", stderrStr,
				)
			}
			return fmt.Errorf("agent subprocess failed: %w (stderr: %s)", waitErr, stderrStr)
		}

		logger.Info("[AGENT-BRIDGE] Python agent completed",
			"session_id", session.ID,
		)
		return nil
	}
}
