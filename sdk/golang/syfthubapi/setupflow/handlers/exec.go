package handlers

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

const (
	execDefaultTimeoutSecs = 120
	execMaxTimeoutSecs     = 600
)

// ExecHandler handles type=exec steps.
// Runs a shell command, inheriting the current environment plus any
// extra env vars declared in the step config.
// The command's stdin/stdout/stderr are connected to the terminal
// so interactive flows (e.g. browser-based OAuth) work naturally.
type ExecHandler struct{}

func (h *ExecHandler) Validate(step *nodeops.SetupStep) error {
	if step.Exec == nil {
		return fmt.Errorf("exec config is required for type 'exec'")
	}
	if step.Exec.Command == "" {
		return fmt.Errorf("exec.command is required")
	}
	if step.Exec.TimeoutSecs < 0 {
		return fmt.Errorf("exec.timeout_secs cannot be negative")
	}
	if step.Exec.TimeoutSecs > execMaxTimeoutSecs {
		return fmt.Errorf("exec.timeout_secs cannot exceed %d", execMaxTimeoutSecs)
	}
	return nil
}

func (h *ExecHandler) Execute(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
	cfg := step.Exec

	timeout := execDefaultTimeoutSecs * time.Second
	if cfg.TimeoutSecs > 0 {
		timeout = time.Duration(cfg.TimeoutSecs) * time.Second
	}

	msg := cfg.Message
	if msg == "" {
		msg = fmt.Sprintf("Running: %s", cfg.Command)
	}
	ctx.IO.Status(msg)

	cmdCtx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	cmd := exec.CommandContext(cmdCtx, "sh", "-c", cfg.Command)

	// When extra env vars are specified, copy the current environment and append them.
	// Otherwise leave cmd.Env nil so Go inherits the parent environment automatically.
	if len(cfg.Env) > 0 {
		cmd.Env = os.Environ()
		for k, v := range cfg.Env {
			cmd.Env = append(cmd.Env, k+"="+v)
		}
	}

	// Connect to terminal so interactive flows (browser OAuth) work
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		if cmdCtx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("command timed out after %v", timeout)
		}
		return nil, fmt.Errorf("command failed: %w", err)
	}

	return &setupflow.StepResult{Value: "ok"}, nil
}
