package containermode

import (
	"context"
	"log/slog"
	"os"
	"testing"
)

func TestEnsureImage_RejectsNonCLIRuntime(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))

	// mockRuntime is defined in cleanup_test.go — it's not a *CLIRuntime.
	err := EnsureImage(context.Background(), &mockRuntime{}, "test:latest", logger)
	if err == nil {
		t.Fatal("expected error for non-CLIRuntime")
	}
}

func TestImageExists_ReturnsFalseForMissing(t *testing.T) {
	exists := imageExists(context.Background(), "docker", "syfthub-nonexistent-test-image:never")
	if exists {
		t.Error("should return false for a nonexistent image")
	}
}

func TestRunnerFS_ContainsDockerfile(t *testing.T) {
	data, err := runnerFS.ReadFile("runner/Dockerfile")
	if err != nil {
		t.Fatalf("embedded runner/Dockerfile not found: %v", err)
	}
	if len(data) == 0 {
		t.Error("embedded Dockerfile is empty")
	}
}

func TestRunnerFS_ContainsAllFiles(t *testing.T) {
	expected := []string{
		"runner/Dockerfile",
		"runner/entrypoint.sh",
		"runner/__init__.py",
		"runner/__main__.py",
		"runner/server.py",
		"runner/session.py",
		"runner/policy.py",
	}

	for _, path := range expected {
		if _, err := runnerFS.ReadFile(path); err != nil {
			t.Errorf("missing embedded file %s: %v", path, err)
		}
	}
}
