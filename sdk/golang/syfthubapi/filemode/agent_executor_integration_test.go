package filemode

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// allowExecutor is a policy Executor that allows every check — pre returns
// allowed, post echoes the supplied output back unchanged. The artificial
// delay mimics the latency of the real subprocess policy runner.
type allowExecutor struct{}

func (allowExecutor) Execute(_ context.Context, in *syfthubapi.ExecutorInput) (*syfthubapi.ExecutorOutput, error) {
	time.Sleep(300 * time.Millisecond) // mimic `python -m policy_manager.runner` latency
	if in.PolicyPhase == syfthubapi.PolicyPhasePre {
		return &syfthubapi.ExecutorOutput{
			Success:      true,
			PolicyResult: &syfthubapi.PolicyResultOutput{Allowed: true},
		}, nil
	}
	return &syfthubapi.ExecutorOutput{
		Success:      true,
		Result:       in.Output,
		PolicyResult: &syfthubapi.PolicyResultOutput{Allowed: true},
	}, nil
}

func (allowExecutor) Close() error { return nil }

// msgContent extracts the content field of an agent.message event.
func msgContent(ev syfthubapi.AgentEventPayload) string {
	var d struct {
		Content string `json:"content"`
	}
	_ = json.Unmarshal(ev.Data, &d)
	return d.Content
}

// TestAgentExecutor_RealRuntime_RelaysReply runs AgentExecutor wrapping the
// REAL filemode subprocess agent runtime (an actual runner.py) and asserts the
// agent's reply reaches the outer session. This reproduces the desktop path
// that the unit tests (with a fake inner handler) do not cover.
func TestAgentExecutor_RealRuntime_RelaysReply(t *testing.T) {
	py, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not found")
	}

	dir := t.TempDir()
	runnerPath := filepath.Join(dir, "runner.py")
	// A minimal agent: reply once, then wait for input (like basic-agent —
	// it does NOT return after the first reply).
	runnerSrc := "def handler(session):\n" +
		"    session.send_message('REPLY-FROM-AGENT')\n" +
		"    while True:\n" +
		"        resp = session.request_input('anything else?')\n" +
		"        c = (resp or {}).get('content', '')\n" +
		"        if not c or c == 'done':\n" +
		"            break\n" +
		"        session.send_message('echo:' + c)\n"
	if err := os.WriteFile(runnerPath, []byte(runnerSrc), 0o644); err != nil {
		t.Fatal(err)
	}

	silent := slog.New(slog.NewTextHandler(io.Discard, nil))

	rawHandler := NewAgentHandler(&AgentHandlerConfig{
		PythonPath: py,
		RunnerPath: runnerPath,
		WorkDir:    dir,
		Logger:     silent,
	})

	wrapped := syfthubapi.NewAgentExecutor(rawHandler, allowExecutor{}, "ep", silent).Handler()

	outer := syfthubapi.NewAgentSession(context.Background(), syfthubapi.AgentSessionParams{
		ID:     "itest",
		Prompt: "hello",
		User:   &syfthubapi.UserContext{Username: "alice"},
	})
	outer.RunHandler(wrapped)

	var replies []string
	deliveredFollowUp := false
	timer := time.NewTimer(25 * time.Second)
	defer timer.Stop()
loop:
	for {
		select {
		case ev, ok := <-outer.SendCh():
			if !ok {
				break loop
			}
			t.Logf("outer event: %s", ev.EventType)
			if ev.EventType == syfthubapi.EventTypeAgentMessage {
				replies = append(replies, msgContent(ev))
				if !deliveredFollowUp {
					// First reply received — send a follow-up turn through
					// relayInbound (pre-check) and expect the echo back.
					deliveredFollowUp = true
					outer.DeliverMessage(syfthubapi.UserMessage{
						Type: syfthubapi.UserMessageTypeMessage, Content: "ping",
					})
				} else {
					outer.CancelByUser() // got both replies — end the session
				}
			}
		case <-timer.C:
			outer.CancelByUser()
			t.Fatalf("timed out; replies so far: %v", replies)
		}
	}

	if len(replies) < 2 {
		t.Fatalf("expected 2 replies (turn 1 + follow-up echo), got %v", replies)
	}
	if replies[0] != "REPLY-FROM-AGENT" {
		t.Errorf("turn 1 reply = %q, want %q", replies[0], "REPLY-FROM-AGENT")
	}
	if replies[1] != "echo:ping" {
		t.Errorf("follow-up reply = %q, want %q", replies[1], "echo:ping")
	}
}

// hasPolicyManager reports whether the given python can import policy_manager.
func hasPolicyManager(python string) bool {
	if _, err := os.Stat(python); err != nil {
		return false
	}
	return exec.Command(python, "-c", "import policy_manager").Run() == nil
}

// TestAgentExecutor_RealRuntime_ManualReviewSubstitutes is the definitive
// reproduction of the desktop manual-review path: a REAL filemode agent
// wrapped by AgentExecutor whose policy executor is a REAL SubprocessExecutor
// running the actual policy_manager.runner with a manual_review policy. It
// asserts the agent's reply is substituted with the manual-review placeholder
// and that placeholder reaches the caller.
func TestAgentExecutor_RealRuntime_ManualReviewSubstitutes(t *testing.T) {
	pmPython := os.Getenv("POLICY_MANAGER_PYTHON")
	if !hasPolicyManager(pmPython) {
		t.Skip("set POLICY_MANAGER_PYTHON to a python with policy_manager installed")
	}
	py, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not found")
	}

	dir := t.TempDir()
	runnerPath := filepath.Join(dir, "runner.py")
	runnerSrc := "def handler(session):\n" +
		"    session.send_message('REPLY-FROM-AGENT')\n" +
		"    while True:\n" +
		"        resp = session.request_input('anything else?')\n" +
		"        if not (resp or {}).get('content'):\n" +
		"            break\n"
	if err := os.WriteFile(runnerPath, []byte(runnerSrc), 0o644); err != nil {
		t.Fatal(err)
	}

	silent := slog.New(slog.NewTextHandler(io.Discard, nil))

	// Real agent runtime.
	rawHandler := NewAgentHandler(&AgentHandlerConfig{
		PythonPath: py, RunnerPath: runnerPath, WorkDir: dir, Logger: silent,
	})

	// Real policy executor — runs the actual policy_manager.runner with a
	// manual_review policy and a SQLite store.
	polExec, err := NewSubprocessExecutor(&ExecutorConfig{
		PythonPath: pmPython,
		// RunnerPath must point at an existing file (NewSubprocessExecutor
		// stats it); the policy runner is what actually runs under
		// UsePolicyRunner, so the agent's own runner.py is reused here.
		RunnerPath:      runnerPath,
		WorkDir:         dir,
		Logger:          silent,
		UsePolicyRunner: true,
		PolicyConfigs: []syfthubapi.PolicyConfig{
			{Name: "manual_review", Type: "manual_review", Config: map[string]any{}},
		},
		StoreConfig: &syfthubapi.StoreConfig{Type: "sqlite", Path: filepath.Join(dir, "store.db")},
	})
	if err != nil {
		t.Fatalf("NewSubprocessExecutor: %v", err)
	}
	defer polExec.Close()

	wrapped := syfthubapi.NewAgentExecutor(rawHandler, polExec, "ep", silent).Handler()

	outer := syfthubapi.NewAgentSession(context.Background(), syfthubapi.AgentSessionParams{
		ID:     "mr-itest",
		Prompt: "Hello World",
		User:   &syfthubapi.UserContext{Username: "alice"},
	})
	outer.RunHandler(wrapped)

	var reply string
	gotReply := false
	timer := time.NewTimer(40 * time.Second)
	defer timer.Stop()
loop:
	for {
		select {
		case ev, ok := <-outer.SendCh():
			if !ok {
				break loop
			}
			t.Logf("outer event: %s", ev.EventType)
			if ev.EventType == syfthubapi.EventTypeAgentMessage {
				reply = msgContent(ev)
				gotReply = true
				outer.CancelByUser()
			}
		case <-timer.C:
			outer.CancelByUser()
			t.Fatal("timed out waiting for an agent.message on the outer session")
		}
	}

	if !gotReply {
		t.Fatal("no agent.message reached the caller — the manual-review reply was lost")
	}
	t.Logf("caller received: %q", reply)
	if strings.Contains(reply, "REPLY-FROM-AGENT") {
		t.Errorf("manual_review must substitute the reply; the real reply leaked: %q", reply)
	}
	if !strings.Contains(strings.ToLower(reply), "manual review") {
		t.Errorf("expected the manual-review placeholder; got %q", reply)
	}
}
