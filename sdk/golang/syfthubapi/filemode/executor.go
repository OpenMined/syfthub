package filemode

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// SubprocessExecutor executes Python handlers in subprocesses.
type SubprocessExecutor struct {
	pythonPath      string
	runnerPath      string
	workDir         string
	env             []string
	baseEnv         []string // cached os.Environ() snapshot from construction time
	timeout         time.Duration
	logger          *slog.Logger
	policyConfigs   []syfthubapi.PolicyConfig
	storeConfig     *syfthubapi.StoreConfig
	usePolicyRunner bool // Use policy_manager.runner instead of inline script

	mu     sync.RWMutex
	closed bool
}

// ExecutorConfig holds executor configuration.
type ExecutorConfig struct {
	PythonPath      string
	RunnerPath      string
	WorkDir         string
	Env             []string
	Timeout         time.Duration
	Logger          *slog.Logger
	PolicyConfigs   []syfthubapi.PolicyConfig
	StoreConfig     *syfthubapi.StoreConfig
	UsePolicyRunner bool // Use policy_manager.runner instead of inline script
}

// NewSubprocessExecutor creates a new subprocess executor.
func NewSubprocessExecutor(cfg *ExecutorConfig) (*SubprocessExecutor, error) {
	pythonPath := cfg.PythonPath
	if pythonPath == "" {
		pythonPath = "python3"
	}

	timeout := cfg.Timeout
	if timeout == 0 {
		timeout = 30 * time.Second
	}

	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	// Verify Python is available
	if _, err := exec.LookPath(pythonPath); err != nil {
		return nil, fmt.Errorf("python not found at %s: %w", pythonPath, err)
	}

	// Verify runner exists
	if _, err := os.Stat(cfg.RunnerPath); err != nil {
		return nil, fmt.Errorf("runner not found at %s: %w", cfg.RunnerPath, err)
	}

	return &SubprocessExecutor{
		pythonPath:      pythonPath,
		runnerPath:      cfg.RunnerPath,
		workDir:         cfg.WorkDir,
		env:             cfg.Env,
		baseEnv:         os.Environ(),
		timeout:         timeout,
		logger:          logger,
		policyConfigs:   cfg.PolicyConfigs,
		storeConfig:     cfg.StoreConfig,
		usePolicyRunner: cfg.UsePolicyRunner,
	}, nil
}

// Execute runs the Python handler with the given input.
func (e *SubprocessExecutor) Execute(ctx context.Context, input *syfthubapi.ExecutorInput) (*syfthubapi.ExecutorOutput, error) {
	e.mu.RLock()
	closed := e.closed
	e.mu.RUnlock()
	if closed {
		return nil, fmt.Errorf("executor is closed")
	}

	e.logger.Debug("[POLICY-EXEC] starting execution",
		"endpoint_type", input.Type,
		"use_policy_runner", e.usePolicyRunner,
		"policy_count", len(e.policyConfigs),
		"work_dir", e.workDir,
	)

	if input.Context != nil {
		e.logger.Debug("[POLICY-EXEC] request context",
			"user_id", input.Context.UserID,
			"endpoint_slug", input.Context.EndpointSlug,
			"endpoint_type", input.Context.EndpointType,
		)
	}

	// Create context with timeout
	ctx, cancel := context.WithTimeout(ctx, e.timeout)
	defer cancel()

	var cmd *exec.Cmd

	if e.usePolicyRunner {
		e.logger.Debug("[POLICY-EXEC] Using policy_manager.runner for policy-aware execution")
		cmd = e.buildPolicyRunnerCommand(ctx)
	} else {
		e.logger.Debug("[POLICY-EXEC] Using legacy inline wrapper (NO POLICY ENFORCEMENT)")
		cmd = e.buildLegacyCommand(ctx)
	}

	if cmd == nil {
		e.logger.Error("[POLICY-EXEC] Failed to build command")
		return nil, fmt.Errorf("failed to build command")
	}

	e.logger.Debug("[POLICY-EXEC] Command built",
		"path", cmd.Path,
		"args", cmd.Args,
	)

	// Serialize input to JSON
	inputJSON, err := e.serializeInput(input)
	if err != nil {
		e.logger.Error("[POLICY-EXEC] Failed to serialize input", "error", err)
		return nil, err
	}

	e.logger.Debug("[POLICY-EXEC] Serialized input JSON",
		"length", len(inputJSON),
	)

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	// stdout is capped at maxStdoutBytes to prevent OOM from a runaway handler.
	// stderr is left unbounded because it is small in practice and drains on
	// process exit; bounding it would risk truncating Python tracebacks needed
	// for diagnostics.
	stdout := &limitedBuffer{cap: maxStdoutBytes}
	var stderr bytes.Buffer
	cmd.Stdout = stdout
	cmd.Stderr = &stderr

	e.logger.Debug("[POLICY-EXEC] starting Python process",
		"python_path", e.pythonPath,
		"runner_path", e.runnerPath,
	)
	if err := cmd.Start(); err != nil {
		e.logger.Error("[POLICY-EXEC] Failed to start process", "error", err)
		return nil, fmt.Errorf("failed to start process: %w", err)
	}

	// Write input and close stdin
	if _, err := stdin.Write(inputJSON); err != nil {
		stdin.Close()
		cmd.Process.Kill()
		e.logger.Error("[POLICY-EXEC] Failed to write input to process", "error", err)
		return nil, fmt.Errorf("failed to write input: %w", err)
	}
	stdin.Close()

	// Wait for completion
	err = cmd.Wait()

	// Check for timeout
	if ctx.Err() == context.DeadlineExceeded {
		e.logger.Error("[POLICY-EXEC] Execution timed out", "timeout", e.timeout.String())
		return nil, &syfthubapi.TimeoutError{
			Operation: "handler execution",
			Duration:  e.timeout.String(),
		}
	}

	if stderr.Len() > 0 {
		e.logger.Debug("[POLICY-EXEC] python stderr", "stderr", stderr.String())
	}

	e.logger.Debug("[POLICY-EXEC] python stdout",
		"length", stdout.Len(),
		"content", stdout.String(),
	)

	// Parse output even if there was an error (handler might have returned error JSON)
	if stdout.Len() > 0 {
		var output syfthubapi.ExecutorOutput
		if err := json.Unmarshal(stdout.Bytes(), &output); err != nil {
			e.logger.Error("[POLICY-EXEC] Failed to parse handler output",
				"stdout", stdout.String(),
				"error", err,
			)
			return nil, fmt.Errorf("failed to parse output: %w (stderr: %s)", err, stderr.String())
		}

		if output.PolicyResult != nil {
			e.logger.Debug("[POLICY-EXEC] policy enforcement result",
				"allowed", output.PolicyResult.Allowed,
				"policy_name", output.PolicyResult.PolicyName,
				"pending", output.PolicyResult.Pending,
			)
		} else if len(e.policyConfigs) > 0 {
			e.logger.Warn("[POLICY-EXEC] no policy result in output - policies may not be enforced")
		}

		e.logger.Info("[POLICY-EXEC] execution complete",
			"success", output.Success,
			"error_type", output.ErrorType,
			"policy_allowed", output.PolicyResult != nil && output.PolicyResult.Allowed,
		)

		return &output, nil
	}

	// No output - return error
	if err != nil {
		e.logger.Error("[POLICY-EXEC] Handler failed with no output",
			"error", err,
			"stderr", stderr.String(),
		)
		return nil, fmt.Errorf("handler failed: %w (stderr: %s)", err, stderr.String())
	}

	e.logger.Error("[POLICY-EXEC] Handler produced no output", "stderr", stderr.String())
	return nil, fmt.Errorf("handler produced no output (stderr: %s)", stderr.String())
}

// buildPolicyRunnerCommand builds command for policy_manager.runner.
func (e *SubprocessExecutor) buildPolicyRunnerCommand(ctx context.Context) *exec.Cmd {
	return newPythonCmd(ctx, e.pythonPath,
		[]string{"-m", "policy_manager.runner"},
		e.workDir, e.baseEnv, e.env,
	)
}

// buildLegacyCommand builds command for legacy inline wrapper script.
func (e *SubprocessExecutor) buildLegacyCommand(ctx context.Context) *exec.Cmd {
	wrapperScript := `
import sys
import json
import traceback
import importlib.util

def main():
    try:
        # Read input from stdin
        input_data = json.loads(sys.stdin.read())

        # Load runner module
        spec = importlib.util.spec_from_file_location("runner", "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["runner"] = runner
        spec.loader.exec_module(runner)

        # Get handler function
        if not hasattr(runner, "handler"):
            raise AttributeError("runner.py must define a 'handler' function")

        handler = runner.handler

        # Build context dict
        context = input_data.get("context", {})
        if context and "metadata" in context:
            context = context["metadata"]

        # Call handler based on type
        if input_data["type"] == "model":
            messages = input_data.get("messages", [])
            result = handler(messages, context)
        else:  # data_source
            query = input_data.get("query", "")
            result = handler(query, context)

        # Handle async functions
        import asyncio
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)

        # Serialize result
        print(json.dumps({"success": True, "result": result}))

    except Exception as e:
        error_info = {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        print(json.dumps(error_info))
        sys.exit(0)  # Exit cleanly so Go can parse the error

if __name__ == "__main__":
    main()
`
	return newPythonCmd(ctx, e.pythonPath,
		[]string{"-c", wrapperScript},
		e.workDir, e.baseEnv, e.env,
	)
}

// serializeInput serializes executor input to JSON.
// For the policy runner path, additional fields are added via a copy to avoid mutating the caller's struct.
func (e *SubprocessExecutor) serializeInput(input *syfthubapi.ExecutorInput) ([]byte, error) {
	toMarshal := input
	if e.usePolicyRunner {
		// Copy so we don't mutate the caller's struct
		copy := *input
		copy.Policies = e.policyConfigs
		copy.Store = e.storeConfig
		copy.HandlerPath = e.runnerPath
		copy.WorkDir = e.workDir
		toMarshal = &copy
	}

	inputJSON, err := json.Marshal(toMarshal)
	if err != nil {
		return nil, fmt.Errorf("failed to serialize input: %w", err)
	}
	return inputJSON, nil
}

// Close closes the executor.
func (e *SubprocessExecutor) Close() error {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.closed = true
	return nil
}
