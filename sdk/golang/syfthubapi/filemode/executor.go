package filemode

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
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
	timeout         time.Duration
	logger          *slog.Logger
	policyConfigs   []syfthubapi.PolicyConfig
	storeConfig     *syfthubapi.StoreConfig
	usePolicyRunner bool // Use policy_manager.runner instead of inline script

	mu     sync.Mutex
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
		timeout:         timeout,
		logger:          logger,
		policyConfigs:   cfg.PolicyConfigs,
		storeConfig:     cfg.StoreConfig,
		usePolicyRunner: cfg.UsePolicyRunner,
	}, nil
}

// Execute runs the Python handler with the given input.
func (e *SubprocessExecutor) Execute(ctx context.Context, input *syfthubapi.ExecutorInput) (*syfthubapi.ExecutorOutput, error) {
	e.mu.Lock()
	if e.closed {
		e.mu.Unlock()
		return nil, fmt.Errorf("executor is closed")
	}
	e.mu.Unlock()

	// Log execution start with context
	e.logger.Info("[POLICY-EXEC] Starting execution",
		"endpoint_type", input.Type,
		"use_policy_runner", e.usePolicyRunner,
		"policy_count", len(e.policyConfigs),
		"work_dir", e.workDir,
	)

	// Log user context if available
	if input.Context != nil {
		e.logger.Info("[POLICY-EXEC] Request context",
			"user_id", input.Context.UserID,
			"endpoint_slug", input.Context.EndpointSlug,
			"endpoint_type", input.Context.EndpointType,
			"metadata", fmt.Sprintf("%+v", input.Context.Metadata),
		)
	}

	// Log query content
	if input.Type == "model" {
		e.logger.Info("[POLICY-EXEC] Model query",
			"messages_count", len(input.Messages),
			"messages", fmt.Sprintf("%+v", input.Messages),
		)
	} else {
		e.logger.Info("[POLICY-EXEC] Data source query",
			"query", input.Query,
		)
	}

	// Log configured policies
	for i, p := range e.policyConfigs {
		e.logger.Info("[POLICY-EXEC] Configured policy",
			"index", i,
			"name", p.Name,
			"type", p.Type,
			"config", fmt.Sprintf("%+v", p.Config),
		)
	}

	// Create context with timeout
	ctx, cancel := context.WithTimeout(ctx, e.timeout)
	defer cancel()

	var cmd *exec.Cmd

	if e.usePolicyRunner {
		e.logger.Info("[POLICY-EXEC] Using policy_manager.runner for policy-aware execution")
		// Use policy_manager.runner for policy-aware execution
		cmd = e.buildPolicyRunnerCommand(ctx, input)
	} else {
		e.logger.Info("[POLICY-EXEC] Using legacy inline wrapper (NO POLICY ENFORCEMENT)")
		// Use legacy inline wrapper script
		cmd = e.buildLegacyCommand(ctx, input)
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
		"content", string(inputJSON),
	)

	cmd.Dir = e.workDir

	// Hide console window on Windows
	hideWindow(cmd)

	// Set environment
	cmd.Env = append(os.Environ(), e.env...)

	// Setup pipes
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	// Start the process
	e.logger.Info("[POLICY-EXEC] Starting Python process",
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

	// Log stderr if present
	if stderr.Len() > 0 {
		e.logger.Info("[POLICY-EXEC] Python stderr output", "stderr", stderr.String())
	}

	// Log stdout
	e.logger.Info("[POLICY-EXEC] Python stdout output",
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

		// Log policy result if present
		e.logger.Info("[POLICY-EXEC] Execution result",
			"success", output.Success,
			"has_error", output.Error != "",
			"error", output.Error,
			"error_type", output.ErrorType,
		)

		if output.PolicyResult != nil {
			e.logger.Info("[POLICY-EXEC] POLICY ENFORCEMENT RESULT",
				"allowed", output.PolicyResult.Allowed,
				"policy_name", output.PolicyResult.PolicyName,
				"reason", output.PolicyResult.Reason,
				"pending", output.PolicyResult.Pending,
				"metadata", fmt.Sprintf("%+v", output.PolicyResult.Metadata),
			)
		} else {
			e.logger.Warn("[POLICY-EXEC] No policy result in output - policies may not be enforced")
		}

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
func (e *SubprocessExecutor) buildPolicyRunnerCommand(ctx context.Context, input *syfthubapi.ExecutorInput) *exec.Cmd {
	return exec.CommandContext(ctx, e.pythonPath, "-m", "policy_manager.runner")
}

// buildLegacyCommand builds command for legacy inline wrapper script.
func (e *SubprocessExecutor) buildLegacyCommand(ctx context.Context, input *syfthubapi.ExecutorInput) *exec.Cmd {
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
	return exec.CommandContext(ctx, e.pythonPath, "-c", wrapperScript)
}

// serializeInput serializes executor input to JSON.
func (e *SubprocessExecutor) serializeInput(input *syfthubapi.ExecutorInput) ([]byte, error) {
	// For policy runner, include policy configs and handler path
	if e.usePolicyRunner {
		input.Policies = e.policyConfigs
		input.Store = e.storeConfig
		input.HandlerPath = e.runnerPath
		input.WorkDir = e.workDir
	}

	inputJSON, err := json.Marshal(input)
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

// CreateExecutor creates an executor based on the runtime config.
func CreateExecutor(cfg *ExecutorConfig, runtime *RuntimeConfig) (syfthubapi.Executor, error) {
	// Use venv python if available
	venvPython := filepath.Join(cfg.WorkDir, ".venv", "bin", "python")
	if _, err := os.Stat(venvPython); err == nil {
		cfg.PythonPath = venvPython
	}

	return NewSubprocessExecutor(cfg)
}
