package containermode

import (
	"context"
	"log/slog"
	"os"
	"strings"
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
		nil,
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
		nil,
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
		nil,
	)
	if err == nil {
		t.Fatal("expected error for non-CLIRuntime with Dockerfile")
	}
}

func TestGetImageLabel_ReturnsEmptyOnMissing(t *testing.T) {
	labels, _ := getImageLabels(context.Background(), "docker", "syfthub-nonexistent-test-image:never", "syfthub.dockerfile.hash")
	if got := labels["syfthub.dockerfile.hash"]; got != "" {
		t.Errorf("expected empty label for nonexistent image, got %q", got)
	}
}

func TestRunnerFS_ContainsAllFiles(t *testing.T) {
	// The embedded runner/ dir is the build context for the default
	// endpoint image. Files listed here MUST exist; the Dockerfile COPYs
	// them into /usr/local/lib/syft_runtime/ and runs the bwrap probe.
	expected := []string{
		"runner/Dockerfile",
		"runner/server.py",       // in-container HTTP multiplexer
		"runner/syft_entry.py",   // in-bwrap loader
		"runner/_syft_audit.py",  // audit hook (imported explicitly, NOT sitecustomize)
		"runner/session_loop.py", // in-bwrap AgentSession
		"runner/probe.sh",        // bwrap verification probe
	}

	for _, path := range expected {
		if _, err := runnerFS.ReadFile(path); err != nil {
			t.Errorf("missing embedded file %s: %v", path, err)
		}
	}
}

func TestBuildAugmentedDockerfile(t *testing.T) {
	user := "FROM python:3.11-slim\nRUN pip install requests\n"
	got := buildAugmentedDockerfile(user)
	if !strings.HasPrefix(got, user) {
		t.Errorf("augmented Dockerfile should start with user's content; got: %q", got[:min(len(got), 80)])
	}
	if !strings.Contains(got, "syfthub sandbox patch layer") {
		t.Error("augmented Dockerfile missing sandbox patch marker")
	}
	if !strings.Contains(got, "bubblewrap") {
		t.Error("augmented Dockerfile missing bubblewrap install")
	}
	if !strings.Contains(got, "/usr/local/lib/syft_runtime/server.py") {
		t.Error("augmented Dockerfile missing entrypoint to server.py")
	}
	if !strings.Contains(got, `syfthub.sandbox.bwrap="verified"`) {
		t.Error("augmented Dockerfile missing verified label")
	}
}

func TestBuildAugmentedDockerfile_AddsNewlineWhenMissing(t *testing.T) {
	// User's Dockerfile without trailing newline: the patch must not glue
	// onto the last directive.
	user := "FROM python:3.11-slim"
	got := buildAugmentedDockerfile(user)
	if !strings.Contains(got, "FROM python:3.11-slim\n") {
		t.Errorf("augmented Dockerfile glued patch onto user's last line: %q", got)
	}
}
