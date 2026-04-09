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

func TestResolveEndpointImage_DefaultFallback(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))

	// When no registry image and no Dockerfile, should return default.
	image, err := ResolveEndpointImage(
		context.Background(),
		&mockRuntime{}, // unused in default path
		"my-model", "/tmp/nonexistent",
		"",    // no registry image
		false, // no Dockerfile
		"syfthub/endpoint-runner:latest",
		logger,
	)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if image != "syfthub/endpoint-runner:latest" {
		t.Errorf("image = %q, want default", image)
	}
}

func TestResolveEndpointImage_RejectsNonCLIRuntime(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))

	// Registry image path requires *CLIRuntime.
	_, err := ResolveEndpointImage(
		context.Background(),
		&mockRuntime{},
		"my-model", "/tmp/test",
		"myorg/custom:v1", // registry image triggers CLI runtime check
		false,
		"default:latest",
		logger,
	)
	if err == nil {
		t.Fatal("expected error for non-CLIRuntime with registry image")
	}

	// Dockerfile path also requires *CLIRuntime.
	_, err = ResolveEndpointImage(
		context.Background(),
		&mockRuntime{},
		"my-model", "/tmp/test",
		"",   // no registry image
		true, // has Dockerfile
		"default:latest",
		logger,
	)
	if err == nil {
		t.Fatal("expected error for non-CLIRuntime with Dockerfile")
	}
}

func TestGetImageLabel_ReturnsEmptyOnMissing(t *testing.T) {
	label := getImageLabel(context.Background(), "docker", "syfthub-nonexistent-test-image:never", "syfthub.dockerfile.hash")
	if label != "" {
		t.Errorf("expected empty label for nonexistent image, got %q", label)
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
