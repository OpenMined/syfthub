package handlers

import (
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

func TestExec_Validate_NilConfig(t *testing.T) {
	h := &ExecHandler{}
	step := &nodeops.SetupStep{Exec: nil}
	if err := h.Validate(step); err == nil {
		t.Fatal("expected error for nil exec config")
	}
}

func TestExec_Validate_EmptyCommand(t *testing.T) {
	h := &ExecHandler{}
	step := &nodeops.SetupStep{Exec: &nodeops.ExecConfig{Command: ""}}
	if err := h.Validate(step); err == nil {
		t.Fatal("expected error for empty command")
	}
}

func TestExec_Validate_TimeoutExceeds600(t *testing.T) {
	h := &ExecHandler{}
	step := &nodeops.SetupStep{Exec: &nodeops.ExecConfig{Command: "echo hi", TimeoutSecs: 601}}
	if err := h.Validate(step); err == nil {
		t.Fatal("expected error for timeout > 600")
	}
}

func TestExec_Validate_Valid(t *testing.T) {
	h := &ExecHandler{}
	step := &nodeops.SetupStep{Exec: &nodeops.ExecConfig{Command: "echo hi", TimeoutSecs: 30}}
	if err := h.Validate(step); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestExec_Execute_SimpleCommand(t *testing.T) {
	h := &ExecHandler{}
	io := &testIO{}
	step := &nodeops.SetupStep{
		Exec: &nodeops.ExecConfig{Command: "echo hello"},
	}
	ctx := &setupflow.SetupContext{IO: io}

	result, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Value != "ok" {
		t.Errorf("expected value 'ok', got %q", result.Value)
	}
	if len(io.statusMessages) == 0 {
		t.Fatal("expected at least one status message")
	}
	if io.statusMessages[0] != "Running: echo hello" {
		t.Errorf("expected default status message, got %q", io.statusMessages[0])
	}
}

func TestExec_Execute_CustomMessage(t *testing.T) {
	h := &ExecHandler{}
	io := &testIO{}
	step := &nodeops.SetupStep{
		Exec: &nodeops.ExecConfig{
			Command: "true",
			Message: "Installing dependencies",
		},
	}
	ctx := &setupflow.SetupContext{IO: io}

	_, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if io.statusMessages[0] != "Installing dependencies" {
		t.Errorf("expected custom message, got %q", io.statusMessages[0])
	}
}

func TestExec_Execute_WithEnvVars(t *testing.T) {
	h := &ExecHandler{}
	io := &testIO{}
	step := &nodeops.SetupStep{
		Exec: &nodeops.ExecConfig{
			Command: "test \"$MY_TEST_VAR\" = \"hello_from_exec\"",
			Env:     map[string]string{"MY_TEST_VAR": "hello_from_exec"},
		},
	}
	ctx := &setupflow.SetupContext{IO: io}

	_, err := h.Execute(step, ctx)
	if err != nil {
		t.Fatalf("env var should be set: %v", err)
	}
}

func TestExec_Execute_FailingCommand(t *testing.T) {
	h := &ExecHandler{}
	io := &testIO{}
	step := &nodeops.SetupStep{
		Exec: &nodeops.ExecConfig{Command: "false"},
	}
	ctx := &setupflow.SetupContext{IO: io}

	_, err := h.Execute(step, ctx)
	if err == nil {
		t.Fatal("expected error for failing command")
	}
	if got := err.Error(); got != "command failed: exit status 1" {
		t.Errorf("unexpected error message: %q", got)
	}
}

func TestExec_Execute_Timeout(t *testing.T) {
	h := &ExecHandler{}
	io := &testIO{}
	step := &nodeops.SetupStep{
		Exec: &nodeops.ExecConfig{
			Command:     "sleep 10",
			TimeoutSecs: 1,
		},
	}
	ctx := &setupflow.SetupContext{IO: io}

	_, err := h.Execute(step, ctx)
	if err == nil {
		t.Fatal("expected timeout error")
	}
	if got := err.Error(); got != "command timed out after 1s" {
		t.Errorf("unexpected error message: %q", got)
	}
}
