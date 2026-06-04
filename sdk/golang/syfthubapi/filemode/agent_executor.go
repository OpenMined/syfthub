package filemode

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// filepathAbs / osOpen / pathIsUnder are tiny indirections so the runner-
// attachment helper is easy to test (and easy to retarget if we later want
// to support mounted virtual paths).

func filepathAbs(p string) (string, error) {
	return filepath.Abs(p)
}

func osOpen(p string) (*os.File, error) {
	return os.Open(p)
}

// pathIsUnder reports whether absPath is the same as or a descendant of absDir.
// Both arguments must be absolute and cleaned.
func pathIsUnder(absPath, absDir string) bool {
	if absPath == absDir {
		return true
	}
	withSep := absDir
	if !strings.HasSuffix(withSep, string(filepath.Separator)) {
		withSep += string(filepath.Separator)
	}
	return strings.HasPrefix(absPath, withSep)
}

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
//
// The AgentSession class defined here intentionally mirrors the AgentSession
// class in containermode/runner/session_loop.py. Both speak JSON-lines on
// stdin/stdout (the container runtime's bwrap child runs session_loop.py via
// syft_entry.py). Their PUBLIC METHOD NAMES and EVENT TYPE STRINGS MUST stay
// identical so the same user-written runner.py works in both modes.
//
// Public surface (keep in sync with containermode/runner/session_loop.py AgentSession):
//   - send_message(content)                          → event "agent.message"
//   - send_thinking(content)                         → event "agent.thinking"
//   - send_status(status, detail="")                 → event "agent.status"
//   - send_tool_call(tool_name, arguments, ...)      → event "agent.tool_call"
//   - send_tool_result(tool_call_id, ...)            → event "agent.tool_result"
//   - send_token(token)                              → event "agent.token"
//   - send_attachment(path, mime=None, name=None)    → event "agent.attachment"
//   - receive()                                      → blocks for user message
//   - receive_attachment(timeout=None)               → next inbound attachment dict
//   - attachments_dir                                → tempdir for inbound files
//   - request_input(prompt)                          → event "agent.request_input"
//   - request_confirmation(action, ...)              → tool_call w/ requires_confirmation
//
// Method-signature + event-name drift between the two implementations is
// caught at code-review time; any change to one side must be mirrored to
// the other.
const agentWrapperScript = `
import sys
import json
import os
import threading
import queue
import importlib.util
import traceback


class AgentSession:
    """Bidirectional agent session communicating via stdin/stdout JSON-lines."""

    def __init__(self, data):
        self.id = data.get("session_id", "")
        self.prompt = data.get("prompt", "")
        self.messages = data.get("messages", [])
        self.config = data.get("config", {})
        # attachments_dir, when non-empty, is a per-session tempdir on the host
        # where inbound attachment plaintexts have been materialized. The
        # runner reads files from this dir for inbound attachments and writes
        # outbound attachment files here before calling send_attachment().
        self.attachments_dir = data.get("attachments_dir", "")
        self._write_lock = threading.Lock()
        self._tc_counter = 0
        # Inbound attachments arrive as separate JSON frames on stdin, so we
        # demultiplex stdin into two queues read by a single dispatcher thread.
        self._messages: queue.Queue = queue.Queue()
        self._attachments: queue.Queue = queue.Queue()
        self._cancelled = False
        self._stdin_thread = threading.Thread(target=self._read_stdin_loop, daemon=True)
        self._stdin_thread.start()

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
                       description="", requires_confirmation=False,
                       display=""):
        """Send a tool call event.

        display is an optional renderer hint (e.g. "terminal", "code",
        "diff", "web") for the chat UI. When omitted the consumer falls
        back to a name-based lookup or the generic renderer. See
        agenttypes.ToolCall.Display for the wire-level contract.
        """
        if tool_call_id is None:
            self._tc_counter += 1
            tool_call_id = f"tc-{self._tc_counter}"
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "description": description,
            "requires_confirmation": requires_confirmation,
        }
        if display:
            payload["display"] = display
        self._emit("agent.tool_call", payload)

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

    def send_attachment(self, path, mime=None, name=None):
        """Send a file attachment to the user.

        The host bridge reads the file off disk, encrypts + uploads (or inlines
        for small files), and emits the agent.attachment event. The Python
        runner just hands over a path.

        Args:
            path: filesystem path to the file (str or os.PathLike)
            mime: MIME type (default "application/octet-stream")
            name: display name (default os.path.basename(path))
        """
        path_str = os.fspath(path)
        if not os.path.isfile(path_str):
            raise FileNotFoundError(path_str)
        payload = {
            "path": path_str,
            "mime": mime or "application/octet-stream",
            "name": name or os.path.basename(path_str),
        }
        # Distinct envelope type — read by the Go bridge in a different arm
        # than agent.* events. See filemode/agent_executor.go.
        self._emit_raw({"type": "agent_attachment", "payload": payload})

    def receive(self, timeout=None):
        """Block until a user message arrives. Returns dict with 'type' and 'content'."""
        try:
            msg = self._messages.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(msg, _Cancelled):
            raise KeyboardInterrupt("Session cancelled by user")
        return msg

    def receive_attachment(self, timeout=None):
        """Block until an inbound attachment arrives, or return None on timeout.

        Returns a dict with keys: file_id, path, name, mime, size_bytes, sha256.
        """
        try:
            return self._attachments.get(timeout=timeout)
        except queue.Empty:
            return None

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
        if response is None:
            return False
        return response.get("type") == "user_confirm"

    def _emit(self, event_type, data):
        self._emit_raw({"type": event_type, "data": data})

    def _emit_raw(self, frame):
        with self._write_lock:
            sys.stdout.write(json.dumps(frame) + "\n")
            sys.stdout.flush()

    def _read_stdin_loop(self):
        """Demultiplex stdin frames into message vs. attachment queues."""
        for line in sys.stdin:
            try:
                frame = json.loads(line)
            except Exception:
                continue
            t = frame.get("type", "")
            if t == "cancel":
                self._cancelled = True
                self._messages.put(_Cancelled())
                self._attachments.put(_Cancelled())
                return
            if t == "user_attachment":
                self._attachments.put(frame.get("attachment", {}))
                continue
            # default: user_message-style frame
            self._messages.put(frame.get("message", {}))


class _Cancelled:
    pass


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

// handleRunnerAttachment reads a runner-produced file and forwards it as an
// agent.attachment event via the session. The bridge validates the path
// stays inside the session tempdir before reading.
func handleRunnerAttachment(session *syfthubapi.AgentSession, payload []byte, logger *slog.Logger) error {
	if !session.AttachmentsEnabled() {
		return fmt.Errorf("attachments not enabled for session %s", session.ID)
	}
	var att struct {
		Path string `json:"path"`
		Name string `json:"name"`
		MIME string `json:"mime"`
	}
	if err := json.Unmarshal(payload, &att); err != nil {
		return fmt.Errorf("decode runner attachment payload: %w", err)
	}
	if att.Path == "" {
		return fmt.Errorf("empty path")
	}
	// Path-traversal guard: only allow files under the session AttachmentDir.
	absPath, err := filepathAbs(att.Path)
	if err != nil {
		return fmt.Errorf("resolve attachment path: %w", err)
	}
	absDir, err := filepathAbs(session.AttachmentDir)
	if err != nil {
		return fmt.Errorf("resolve attachment dir: %w", err)
	}
	if !pathIsUnder(absPath, absDir) {
		return fmt.Errorf("attachment path %q outside session dir %q", absPath, absDir)
	}

	f, err := osOpen(absPath)
	if err != nil {
		return fmt.Errorf("open attachment %q: %w", absPath, err)
	}
	defer f.Close()
	fileID, err := session.SendAttachment(f, att.Name, att.MIME)
	if err != nil {
		return fmt.Errorf("send attachment: %w", err)
	}
	logger.Debug("[AGENT-BRIDGE] Forwarded runner attachment",
		"session_id", session.ID, "file_id", fileID, "path", absPath)
	return nil
}

// NewAgentHandler creates an AgentHandler that delegates to a Python runner.py subprocess.
// Each session spawns a new long-lived Python subprocess with JSON-lines bidirectional protocol.
func NewAgentHandler(cfg *AgentHandlerConfig) syfthubapi.AgentHandler {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	// Cache the base environment once at construction time so we don't call
	// os.Environ() on every session invocation.
	baseEnv := os.Environ()

	return func(ctx context.Context, session *syfthubapi.AgentSession) error {
		cmd := newPythonCmd(ctx, cfg.PythonPath,
			[]string{"-c", agentWrapperScript},
			cfg.WorkDir, baseEnv, cfg.Env,
		)

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
			"type":            "session_start",
			"session_id":      session.ID,
			"prompt":          session.InitialPrompt,
			"messages":        session.Messages,
			"config":          session.Config,
			"attachments_dir": session.AttachmentDir,
		}
		if err := json.NewEncoder(stdin).Encode(startPayload); err != nil {
			cmd.Process.Kill()
			return fmt.Errorf("failed to write session_start: %w", err)
		}

		var wg sync.WaitGroup

		// Reader goroutine: Python stdout → session events
		wg.Add(1)
		go func() {
			defer wg.Done()
			scanner := bufio.NewScanner(stdout)
			scanner.Buffer(make([]byte, 1024*1024), 1024*1024) // 1MB max line

			for scanner.Scan() {
				var envelope struct {
					Type    string          `json:"type"`
					Data    json.RawMessage `json:"data"`
					Payload json.RawMessage `json:"payload"`
				}
				if err := json.Unmarshal(scanner.Bytes(), &envelope); err != nil {
					logger.Warn("[AGENT-BRIDGE] Failed to parse event",
						"session_id", session.ID,
						"error", err,
					)
					continue
				}

				// Distinct envelope for outbound attachments: the runner has
				// written a file to disk; we now read it, encode + emit the
				// agent.attachment event. See docs/architecture/attachments.md.
				if envelope.Type == "agent_attachment" {
					if err := handleRunnerAttachment(session, envelope.Payload, logger); err != nil {
						logger.Warn("[AGENT-BRIDGE] Failed to forward runner attachment",
							"session_id", session.ID, "error", err)
					}
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

		// Writer goroutine for user messages: session.Receive() → Python stdin
		stdinMu := &sync.Mutex{}
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
				stdinMu.Lock()
				err = stdinEncoder.Encode(wrapper)
				stdinMu.Unlock()
				if err != nil {
					return // stdin closed, Python exited
				}
			}
		}()

		// Writer goroutine for user attachments: session.AttachmentCh → Python stdin
		// Only active when attachments are enabled for this session.
		if session.AttachmentsEnabled() {
			ch := session.AttachmentCh()
			go func() {
				for {
					select {
					case <-session.Context().Done():
						return
					case att, ok := <-ch:
						if !ok {
							return
						}
						wrapper := map[string]any{
							"type": "user_attachment",
							"attachment": map[string]any{
								"file_id":    att.FileID,
								"path":       att.LocalPath,
								"name":       att.Name,
								"mime":       att.MIME,
								"size_bytes": att.SizeBytes,
								"sha256":     att.PlaintextSHA256,
							},
						}
						stdinMu.Lock()
						err := stdinEncoder.Encode(wrapper)
						stdinMu.Unlock()
						if err != nil {
							return // stdin closed
						}
					}
				}
			}()
		}

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
