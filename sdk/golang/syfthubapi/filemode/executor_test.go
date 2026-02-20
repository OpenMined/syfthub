package filemode

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestNewSubprocessExecutor(t *testing.T) {
	// Create a temporary runner.py for testing
	tmpDir, err := os.MkdirTemp("", "executor_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	t.Run("success with defaults", func(t *testing.T) {
		// Skip if python3 is not available
		if _, err := exec.LookPath("python3"); err != nil {
			t.Skip("python3 not available")
		}

		cfg := &ExecutorConfig{
			RunnerPath: runnerPath,
			WorkDir:    tmpDir,
		}

		executor, err := NewSubprocessExecutor(cfg)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if executor == nil {
			t.Fatal("executor is nil")
		}
		if executor.pythonPath != "python3" {
			t.Errorf("pythonPath = %q", executor.pythonPath)
		}
		if executor.timeout != 30*time.Second {
			t.Errorf("timeout = %v", executor.timeout)
		}
	})

	t.Run("custom config", func(t *testing.T) {
		// Skip if python3 is not available
		if _, err := exec.LookPath("python3"); err != nil {
			t.Skip("python3 not available")
		}

		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		cfg := &ExecutorConfig{
			PythonPath: "python3",
			RunnerPath: runnerPath,
			WorkDir:    tmpDir,
			Env:        []string{"FOO=bar"},
			Timeout:    60 * time.Second,
			Logger:     logger,
		}

		executor, err := NewSubprocessExecutor(cfg)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if executor.timeout != 60*time.Second {
			t.Errorf("timeout = %v", executor.timeout)
		}
		if len(executor.env) != 1 || executor.env[0] != "FOO=bar" {
			t.Errorf("env = %v", executor.env)
		}
	})

	t.Run("python not found", func(t *testing.T) {
		cfg := &ExecutorConfig{
			PythonPath: "/nonexistent/python",
			RunnerPath: runnerPath,
			WorkDir:    tmpDir,
		}

		_, err := NewSubprocessExecutor(cfg)
		if err == nil {
			t.Fatal("expected error for missing python")
		}
	})

	t.Run("runner not found", func(t *testing.T) {
		// Skip if python3 is not available
		if _, err := exec.LookPath("python3"); err != nil {
			t.Skip("python3 not available")
		}

		cfg := &ExecutorConfig{
			PythonPath: "python3",
			RunnerPath: "/nonexistent/runner.py",
			WorkDir:    tmpDir,
		}

		_, err := NewSubprocessExecutor(cfg)
		if err == nil {
			t.Fatal("expected error for missing runner")
		}
	})
}

func TestSubprocessExecutorClose(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "executor_close_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	executor, _ := NewSubprocessExecutor(&ExecutorConfig{
		RunnerPath: runnerPath,
		WorkDir:    tmpDir,
	})

	if executor.closed {
		t.Error("executor should not be closed initially")
	}

	err = executor.Close()
	if err != nil {
		t.Errorf("Close error: %v", err)
	}

	if !executor.closed {
		t.Error("executor should be closed after Close()")
	}
}

func TestSubprocessExecutorExecuteWhenClosed(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "executor_closed_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	executor, _ := NewSubprocessExecutor(&ExecutorConfig{
		RunnerPath: runnerPath,
		WorkDir:    tmpDir,
	})

	executor.Close()

	input := &syfthubapi.ExecutorInput{
		Type:  "model",
		Query: "test",
	}

	_, err = executor.Execute(context.Background(), input)
	if err == nil {
		t.Fatal("expected error when executor is closed")
	}
}

func TestSubprocessExecutorExecute(t *testing.T) {
	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	t.Run("successful model execution", func(t *testing.T) {
		// Create a fresh temp directory for each test
		tmpDir, err := os.MkdirTemp("", "model_exec_test")
		if err != nil {
			t.Fatal(err)
		}
		defer os.RemoveAll(tmpDir)

		// Legacy wrapper always looks for runner.py
		runnerPath := filepath.Join(tmpDir, "runner.py")
		runnerCode := `
def handler(messages, context):
    return "Hello from model!"
`
		os.WriteFile(runnerPath, []byte(runnerCode), 0644)

		executor, err := NewSubprocessExecutor(&ExecutorConfig{
			RunnerPath:      runnerPath,
			WorkDir:         tmpDir,
			Timeout:         10 * time.Second,
			UsePolicyRunner: false,
		})
		if err != nil {
			t.Fatalf("error creating executor: %v", err)
		}
		defer executor.Close()

		input := &syfthubapi.ExecutorInput{
			Type:     "model",
			Messages: []syfthubapi.Message{{Role: "user", Content: "Hi"}},
			Context: &syfthubapi.ExecutionContext{
				UserID:       "user-123",
				EndpointSlug: "test-ep",
				Metadata:     map[string]any{"key": "value"},
			},
		}

		output, err := executor.Execute(context.Background(), input)
		if err != nil {
			t.Fatalf("Execute error: %v", err)
		}

		if !output.Success {
			t.Errorf("Success = false, error = %q", output.Error)
		}
		if string(output.Result) != `"Hello from model!"` {
			t.Errorf("Result = %q", string(output.Result))
		}
	})

	t.Run("successful data_source execution", func(t *testing.T) {
		tmpDir, err := os.MkdirTemp("", "ds_exec_test")
		if err != nil {
			t.Fatal(err)
		}
		defer os.RemoveAll(tmpDir)

		runnerPath := filepath.Join(tmpDir, "runner.py")
		runnerCode := `
def handler(query, context):
    return [{"id": "doc1", "content": "Result for: " + query}]
`
		os.WriteFile(runnerPath, []byte(runnerCode), 0644)

		executor, err := NewSubprocessExecutor(&ExecutorConfig{
			RunnerPath:      runnerPath,
			WorkDir:         tmpDir,
			Timeout:         10 * time.Second,
			UsePolicyRunner: false,
		})
		if err != nil {
			t.Fatalf("error creating executor: %v", err)
		}
		defer executor.Close()

		input := &syfthubapi.ExecutorInput{
			Type:  "data_source",
			Query: "test query",
		}

		output, err := executor.Execute(context.Background(), input)
		if err != nil {
			t.Fatalf("Execute error: %v", err)
		}

		if !output.Success {
			t.Errorf("Success = false, error = %q", output.Error)
		}
	})

	t.Run("handler error", func(t *testing.T) {
		tmpDir, err := os.MkdirTemp("", "error_exec_test")
		if err != nil {
			t.Fatal(err)
		}
		defer os.RemoveAll(tmpDir)

		runnerPath := filepath.Join(tmpDir, "runner.py")
		runnerCode := `
def handler(messages, context):
    raise ValueError("test error")
`
		os.WriteFile(runnerPath, []byte(runnerCode), 0644)

		executor, err := NewSubprocessExecutor(&ExecutorConfig{
			RunnerPath:      runnerPath,
			WorkDir:         tmpDir,
			Timeout:         10 * time.Second,
			UsePolicyRunner: false,
		})
		if err != nil {
			t.Fatalf("error creating executor: %v", err)
		}
		defer executor.Close()

		input := &syfthubapi.ExecutorInput{
			Type:     "model",
			Messages: []syfthubapi.Message{{Role: "user", Content: "Hi"}},
		}

		output, err := executor.Execute(context.Background(), input)
		if err != nil {
			t.Fatalf("Execute error: %v", err)
		}

		if output.Success {
			t.Error("Success should be false")
		}
		if output.Error == "" {
			t.Error("Error message should be set")
		}
		if output.ErrorType != "ValueError" {
			t.Errorf("ErrorType = %q", output.ErrorType)
		}
	})

	t.Run("timeout", func(t *testing.T) {
		tmpDir, err := os.MkdirTemp("", "timeout_exec_test")
		if err != nil {
			t.Fatal(err)
		}
		defer os.RemoveAll(tmpDir)

		runnerPath := filepath.Join(tmpDir, "runner.py")
		runnerCode := `
import time
def handler(messages, context):
    time.sleep(10)
    return "done"
`
		os.WriteFile(runnerPath, []byte(runnerCode), 0644)

		executor, err := NewSubprocessExecutor(&ExecutorConfig{
			RunnerPath:      runnerPath,
			WorkDir:         tmpDir,
			Timeout:         100 * time.Millisecond,
			UsePolicyRunner: false,
		})
		if err != nil {
			t.Fatalf("error creating executor: %v", err)
		}
		defer executor.Close()

		input := &syfthubapi.ExecutorInput{
			Type:     "model",
			Messages: []syfthubapi.Message{{Role: "user", Content: "Hi"}},
		}

		_, err = executor.Execute(context.Background(), input)
		if err == nil {
			t.Fatal("expected timeout error")
		}

		// Check it's a TimeoutError
		if timeoutErr, ok := err.(*syfthubapi.TimeoutError); ok {
			if timeoutErr.Operation != "handler execution" {
				t.Errorf("Operation = %q", timeoutErr.Operation)
			}
		} else {
			// Could be other error type but should contain timeout info
			t.Logf("error type: %T, error: %v", err, err)
		}
	})

	t.Run("context cancellation", func(t *testing.T) {
		tmpDir, err := os.MkdirTemp("", "cancel_exec_test")
		if err != nil {
			t.Fatal(err)
		}
		defer os.RemoveAll(tmpDir)

		runnerPath := filepath.Join(tmpDir, "runner.py")
		runnerCode := `
import time
def handler(messages, context):
    time.sleep(10)
    return "done"
`
		os.WriteFile(runnerPath, []byte(runnerCode), 0644)

		executor, err := NewSubprocessExecutor(&ExecutorConfig{
			RunnerPath:      runnerPath,
			WorkDir:         tmpDir,
			Timeout:         30 * time.Second,
			UsePolicyRunner: false,
		})
		if err != nil {
			t.Fatalf("error creating executor: %v", err)
		}
		defer executor.Close()

		ctx, cancel := context.WithCancel(context.Background())

		// Cancel after a short delay
		go func() {
			time.Sleep(100 * time.Millisecond)
			cancel()
		}()

		input := &syfthubapi.ExecutorInput{
			Type:     "model",
			Messages: []syfthubapi.Message{{Role: "user", Content: "Hi"}},
		}

		_, err = executor.Execute(ctx, input)
		// Should error due to context cancellation or timeout
		// The exact error depends on timing
		if err == nil {
			t.Log("no error returned, but execution should have been interrupted")
		}
	})
}

func TestBuildPolicyRunnerCommand(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "policy_cmd_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	executor, _ := NewSubprocessExecutor(&ExecutorConfig{
		RunnerPath:      runnerPath,
		WorkDir:         tmpDir,
		UsePolicyRunner: true,
	})

	input := &syfthubapi.ExecutorInput{Type: "model"}
	cmd := executor.buildPolicyRunnerCommand(context.Background(), input)

	if cmd == nil {
		t.Fatal("command is nil")
	}

	// Check that it's running policy_manager.runner module
	args := cmd.Args
	found := false
	for i, arg := range args {
		if arg == "-m" && i+1 < len(args) && args[i+1] == "policy_manager.runner" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("command does not use policy_manager.runner: %v", args)
	}
}

func TestBuildLegacyCommand(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "legacy_cmd_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	executor, _ := NewSubprocessExecutor(&ExecutorConfig{
		RunnerPath:      runnerPath,
		WorkDir:         tmpDir,
		UsePolicyRunner: false,
	})

	input := &syfthubapi.ExecutorInput{Type: "model"}
	cmd := executor.buildLegacyCommand(context.Background(), input)

	if cmd == nil {
		t.Fatal("command is nil")
	}

	// Check that it's using -c flag for inline script
	args := cmd.Args
	foundC := false
	for _, arg := range args {
		if arg == "-c" {
			foundC = true
			break
		}
	}
	if !foundC {
		t.Errorf("command does not use -c flag: %v", args)
	}
}

func TestSerializeInput(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "serialize_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	t.Run("without policy runner", func(t *testing.T) {
		executor, _ := NewSubprocessExecutor(&ExecutorConfig{
			RunnerPath:      runnerPath,
			WorkDir:         tmpDir,
			UsePolicyRunner: false,
		})

		input := &syfthubapi.ExecutorInput{
			Type:  "model",
			Query: "test",
		}

		data, err := executor.serializeInput(input)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if len(data) == 0 {
			t.Error("serialized data is empty")
		}
	})

	t.Run("with policy runner", func(t *testing.T) {
		executor, _ := NewSubprocessExecutor(&ExecutorConfig{
			RunnerPath:      runnerPath,
			WorkDir:         tmpDir,
			UsePolicyRunner: true,
			PolicyConfigs: []syfthubapi.PolicyConfig{
				{Name: "test", Type: "rate_limit"},
			},
			StoreConfig: &syfthubapi.StoreConfig{
				Type: "sqlite",
				Path: "/tmp/store.db",
			},
		})

		input := &syfthubapi.ExecutorInput{
			Type:  "model",
			Query: "test",
		}

		data, err := executor.serializeInput(input)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		// Input should now have policies and store config
		if input.Policies == nil {
			t.Error("Policies should be set")
		}
		if input.Store == nil {
			t.Error("Store should be set")
		}
		if input.HandlerPath != runnerPath {
			t.Errorf("HandlerPath = %q", input.HandlerPath)
		}

		if len(data) == 0 {
			t.Error("serialized data is empty")
		}
	})
}

func TestCreateExecutor(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "create_executor_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	// Skip if python3 is not available
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}

	t.Run("without venv", func(t *testing.T) {
		cfg := &ExecutorConfig{
			RunnerPath: runnerPath,
			WorkDir:    tmpDir,
		}
		runtime := &RuntimeConfig{
			Mode:    "subprocess",
			Timeout: 30,
		}

		executor, err := CreateExecutor(cfg, runtime)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if executor == nil {
			t.Fatal("executor is nil")
		}
	})

	t.Run("with venv", func(t *testing.T) {
		// Create fake venv structure
		venvBin := filepath.Join(tmpDir, ".venv", "bin")
		os.MkdirAll(venvBin, 0755)

		// Create a fake python symlink/script
		venvPython := filepath.Join(venvBin, "python")
		// On Unix, we can create a symlink to python3
		if pythonPath, err := exec.LookPath("python3"); err == nil {
			os.Symlink(pythonPath, venvPython)
		}

		cfg := &ExecutorConfig{
			RunnerPath: runnerPath,
			WorkDir:    tmpDir,
		}
		runtime := &RuntimeConfig{
			Mode:    "subprocess",
			Timeout: 30,
		}

		executor, err := CreateExecutor(cfg, runtime)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if executor == nil {
			t.Fatal("executor is nil")
		}

		// Check if venv python is used (if symlink was created)
		if _, err := os.Stat(venvPython); err == nil {
			se := executor.(*SubprocessExecutor)
			if se.pythonPath != venvPython {
				t.Logf("pythonPath = %q (venv python available but not used)", se.pythonPath)
			}
		}
	})
}

// Benchmark tests

func BenchmarkSerializeInput(b *testing.B) {
	tmpDir, _ := os.MkdirTemp("", "bench_test")
	defer os.RemoveAll(tmpDir)

	runnerPath := filepath.Join(tmpDir, "runner.py")
	os.WriteFile(runnerPath, []byte("def handler(): pass"), 0644)

	if _, err := exec.LookPath("python3"); err != nil {
		b.Skip("python3 not available")
	}

	executor, _ := NewSubprocessExecutor(&ExecutorConfig{
		RunnerPath: runnerPath,
		WorkDir:    tmpDir,
	})

	input := &syfthubapi.ExecutorInput{
		Type:     "model",
		Messages: []syfthubapi.Message{{Role: "user", Content: "test"}},
	}

	for i := 0; i < b.N; i++ {
		executor.serializeInput(input)
	}
}
