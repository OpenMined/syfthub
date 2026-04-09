package containermode

import (
	"context"
	"crypto/sha256"
	"embed"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// maxBuildOutputBytes caps the in-memory buffer for docker build output.
// Only the last portion is kept for error diagnostics; the rest is discarded.
const maxBuildOutputBytes = 256 * 1024 // 256 KB

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
	cli, err := asCLIRuntime(rt, "EnsureImage")
	if err != nil {
		return err
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

	// Capture tail of combined output for diagnostics on failure.
	// Cap the buffer to avoid OOM on large builds (layer pulls can produce hundreds of MB).
	var output strings.Builder
	lw := &limitedWriter{w: &output, remaining: maxBuildOutputBytes}
	cmd.Stdout = lw
	cmd.Stderr = lw

	if err := cmd.Run(); err != nil {
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

// dockerfileBuildTimeout is the maximum time allowed for building an image
// from an endpoint's Dockerfile. Separate from ContainerConfig.StartTimeout
// because builds can be significantly slower (pulling base images, installing packages).
const dockerfileBuildTimeout = 5 * time.Minute

// ResolveEndpointImage determines which container image to use for a specific
// endpoint. Resolution priority:
//  1. registryImage (from README.md frontmatter container.image) — pull if not local
//  2. hasDockerfile (Dockerfile in endpoint dir) — build with hash-based staleness
//  3. defaultImage (global ContainerConfig.Image)
func ResolveEndpointImage(
	ctx context.Context,
	rt syfthubapi.ContainerRuntime,
	slug, endpointDir string,
	registryImage string,
	hasDockerfile bool,
	defaultImage string,
	logger *slog.Logger,
) (string, error) {
	if registryImage != "" {
		return resolveRegistryImage(ctx, rt, registryImage, logger)
	}
	if hasDockerfile {
		return resolveDockerfileImage(ctx, rt, slug, endpointDir, logger)
	}
	return defaultImage, nil
}

// asCLIRuntime asserts that rt is a *CLIRuntime, returning a typed error if not.
func asCLIRuntime(rt syfthubapi.ContainerRuntime, caller string) (*CLIRuntime, error) {
	cli, ok := rt.(*CLIRuntime)
	if !ok {
		return nil, fmt.Errorf("%s requires a *CLIRuntime, got %T", caller, rt)
	}
	return cli, nil
}

// resolveRegistryImage ensures a registry image is available locally.
// Pulls if not present; does not force-pull existing images.
func resolveRegistryImage(ctx context.Context, rt syfthubapi.ContainerRuntime, image string, logger *slog.Logger) (string, error) {
	cli, err := asCLIRuntime(rt, "ResolveEndpointImage")
	if err != nil {
		return "", err
	}

	if imageExists(ctx, cli.binary, image) {
		logger.Debug("custom registry image already available", "image", image)
		return image, nil
	}

	logger.Info("pulling custom endpoint image", "image", image)
	if err := cli.PullImage(ctx, image); err != nil {
		return "", &syfthubapi.ContainerError{
			Operation: "pull",
			Image:     image,
			Message:   "failed to pull custom endpoint image",
			Cause:     err,
		}
	}

	logger.Info("custom endpoint image pulled successfully", "image", image)
	return image, nil
}

// resolveDockerfileImage builds an image from the endpoint's Dockerfile if
// the image does not exist or the Dockerfile content has changed. Uses a
// SHA-256 hash stored as an image label for staleness detection.
func resolveDockerfileImage(ctx context.Context, rt syfthubapi.ContainerRuntime, slug, endpointDir string, logger *slog.Logger) (string, error) {
	cli, err := asCLIRuntime(rt, "ResolveEndpointImage")
	if err != nil {
		return "", err
	}

	imageName := fmt.Sprintf("syfthub-endpoint-%s:latest", slug)

	dockerfilePath := filepath.Join(endpointDir, "Dockerfile")
	dockerfileContent, err := os.ReadFile(dockerfilePath)
	if err != nil {
		return "", &syfthubapi.ContainerError{
			Operation: "build",
			Image:     imageName,
			Message:   "failed to read Dockerfile",
			Cause:     err,
		}
	}

	currentHash := fmt.Sprintf("%x", sha256.Sum256(dockerfileContent))

	// Check if image exists and is up-to-date.
	if imageExists(ctx, cli.binary, imageName) {
		storedHash := getImageLabel(ctx, cli.binary, imageName, "syfthub.dockerfile.hash")
		if storedHash == currentHash {
			logger.Debug("custom Dockerfile image up-to-date",
				"image", imageName,
				"hash", currentHash[:12],
			)
			return imageName, nil
		}
		logger.Info("Dockerfile changed, rebuilding image",
			"image", imageName,
			"old_hash", storedHash,
			"new_hash", currentHash[:12],
		)
	}

	buildCtx, cancel := context.WithTimeout(ctx, dockerfileBuildTimeout)
	defer cancel()

	logger.Info("building custom endpoint image from Dockerfile",
		"image", imageName,
		"dir", endpointDir,
		"hash", currentHash[:12],
	)

	if err := buildEndpointImage(buildCtx, cli.binary, imageName, endpointDir, currentHash, logger); err != nil {
		return "", &syfthubapi.ContainerError{
			Operation: "build",
			Image:     imageName,
			Message:   "failed to build custom endpoint image",
			Cause:     err,
		}
	}

	logger.Info("custom endpoint image built successfully", "image", imageName)
	return imageName, nil
}

// getImageLabel retrieves a label value from a local image.
// Returns empty string if the label is not found or any error occurs.
func getImageLabel(ctx context.Context, binary, imageName, label string) string {
	format := fmt.Sprintf("{{index .Config.Labels %q}}", label)
	cmd := exec.CommandContext(ctx, binary, "image", "inspect", "--format", format, imageName)
	var out strings.Builder
	cmd.Stdout = &out
	cmd.Stderr = nil
	if err := cmd.Run(); err != nil {
		return ""
	}
	return strings.TrimSpace(out.String())
}

// buildEndpointImage builds an image from a Dockerfile in the given directory,
// tagging it with the specified name and embedding the Dockerfile hash as a label
// for staleness detection on subsequent loads.
func buildEndpointImage(ctx context.Context, binary, imageName, buildDir, dockerfileHash string, logger *slog.Logger) error {
	logger.Debug("building container image", "image", imageName, "context", buildDir)
	cmd := exec.CommandContext(ctx, binary, "build",
		"-t", imageName,
		"--label", fmt.Sprintf("syfthub.dockerfile.hash=%s", dockerfileHash),
		".")
	cmd.Dir = buildDir

	var output strings.Builder
	lw := &limitedWriter{w: &output, remaining: maxBuildOutputBytes}
	cmd.Stdout = lw
	cmd.Stderr = lw

	if err := cmd.Run(); err != nil {
		out := output.String()
		lines := strings.Split(strings.TrimSpace(out), "\n")
		tail := lines
		if len(tail) > 20 {
			tail = tail[len(tail)-20:]
		}
		logger.Error("custom endpoint image build failed",
			"image", imageName,
			"error", err,
			"output_tail", strings.Join(tail, "\n"),
		)
		return fmt.Errorf("image build failed: %w", err)
	}

	return nil
}

// limitedWriter wraps an io.Writer and silently discards bytes once the cap is reached.
// This prevents unbounded memory growth when capturing docker build output.
type limitedWriter struct {
	w         io.Writer
	remaining int
}

func (lw *limitedWriter) Write(p []byte) (int, error) {
	if lw.remaining <= 0 {
		return len(p), nil // discard silently
	}
	if len(p) > lw.remaining {
		p = p[:lw.remaining]
	}
	n, err := lw.w.Write(p)
	lw.remaining -= n
	return len(p), err // report full length to avoid short-write errors from exec
}
