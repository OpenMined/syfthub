package containermode

import (
	"context"
	"embed"
	"fmt"
	"io/fs"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

//go:embed runner/*
var runnerFS embed.FS

// EnsureImage checks if the container image exists locally and builds it from
// the embedded Dockerfile if it does not. This is safe to call multiple times;
// after the first successful build, subsequent calls are a fast no-op (just an
// image inspect).
//
// The runtime parameter must be a *CLIRuntime (the only ContainerRuntime
// implementation). This function is designed to be called by the file provider
// before creating container endpoints.
func EnsureImage(ctx context.Context, rt syfthubapi.ContainerRuntime, imageName string, logger *slog.Logger) error {
	cli, ok := rt.(*CLIRuntime)
	if !ok {
		return fmt.Errorf("EnsureImage requires a *CLIRuntime, got %T", rt)
	}

	// Check if the image already exists.
	if imageExists(ctx, cli.binary, imageName) {
		logger.Debug("container image already exists", "image", imageName)
		return nil
	}

	logger.Info("container image not found, building from embedded Dockerfile", "image", imageName)
	return buildImage(ctx, cli.binary, imageName, logger)
}

// imageExists returns true if the given image is available locally.
func imageExists(ctx context.Context, binary, imageName string) bool {
	cmd := exec.CommandContext(ctx, binary, "image", "inspect", imageName)
	cmd.Stdout = nil
	cmd.Stderr = nil
	return cmd.Run() == nil
}

// buildImage extracts the embedded runner/ directory to a temp dir and runs
// `docker build -t <imageName> .` inside it.
func buildImage(ctx context.Context, binary, imageName string, logger *slog.Logger) error {
	// Extract embedded files to a temp directory.
	buildDir, err := os.MkdirTemp("", "syfthub-image-build-*")
	if err != nil {
		return fmt.Errorf("failed to create build directory: %w", err)
	}
	defer os.RemoveAll(buildDir)

	err = fs.WalkDir(runnerFS, "runner", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}

		// Strip the "runner/" prefix to get the relative path inside buildDir.
		rel, _ := filepath.Rel("runner", path)
		target := filepath.Join(buildDir, rel)

		if d.IsDir() {
			return os.MkdirAll(target, 0755)
		}

		data, err := runnerFS.ReadFile(path)
		if err != nil {
			return fmt.Errorf("read embedded %s: %w", path, err)
		}
		return os.WriteFile(target, data, 0644)
	})
	if err != nil {
		return fmt.Errorf("failed to extract build context: %w", err)
	}

	// Run the build.
	logger.Info("building container image", "image", imageName, "context", buildDir)
	cmd := exec.CommandContext(ctx, binary, "build", "-t", imageName, ".")
	cmd.Dir = buildDir

	// Capture combined output for logging on failure; stream progress on stdout.
	var output strings.Builder
	cmd.Stdout = &output
	cmd.Stderr = &output

	if err := cmd.Run(); err != nil {
		// Log the tail of the build output for diagnostics.
		out := output.String()
		lines := strings.Split(strings.TrimSpace(out), "\n")
		tail := lines
		if len(tail) > 20 {
			tail = tail[len(tail)-20:]
		}
		logger.Error("container image build failed",
			"image", imageName,
			"error", err,
			"output_tail", strings.Join(tail, "\n"),
		)
		return fmt.Errorf("image build failed: %w", err)
	}

	logger.Info("container image built successfully", "image", imageName)
	return nil
}
