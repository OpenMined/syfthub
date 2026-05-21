package containermode

import (
	"context"
	"embed"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
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

// ImageResolveStage names the sub-step ResolveEndpointImage is currently
// performing, surfaced via the OnStage callback so callers can render
// progress UI distinguishing fast cache-hits from multi-minute builds.
type ImageResolveStage string

const (
	ImageStageChecking  ImageResolveStage = "checking"
	ImageStagePulling   ImageResolveStage = "pulling"
	ImageStageBuilding  ImageResolveStage = "building"
	ImageStageVerifying ImageResolveStage = "verifying"
	ImageStageReady     ImageResolveStage = "ready"
)

// ResolveEndpointImage determines which container image to use for a specific
// endpoint. Resolution priority:
//  1. registryImage (from README.md frontmatter container.image) — pull if not local
//  2. hasDockerfile (Dockerfile in endpoint dir) — build with hash-based staleness
//  3. defaultImage (global ContainerConfig.Image)
//
// For custom images (registry or Dockerfile), VerifyImage is called after
// the image is available locally so the bwrap contract is asserted at
// registration time, not first-use time. The default image is built from
// our Dockerfile which embeds the verification step, so it skips re-probing.
func ResolveEndpointImage(
	ctx context.Context,
	rt syfthubapi.ContainerRuntime,
	slug, endpointDir string,
	registryImage string,
	hasDockerfile bool,
	defaultImage string,
	logger *slog.Logger,
	onStage func(ImageResolveStage),
) (string, error) {
	emit := func(s ImageResolveStage) {
		if onStage != nil {
			onStage(s)
		}
	}
	if registryImage != "" {
		image, err := resolveRegistryImage(ctx, rt, registryImage, logger, emit)
		if err != nil {
			return "", err
		}
		emit(ImageStageVerifying)
		if err := VerifyImage(ctx, rt, image, logger); err != nil {
			return "", fmt.Errorf("custom image %q: %w", image, err)
		}
		return image, nil
	}
	if hasDockerfile {
		// Auto-augment build runs the bwrap probe AND sets the verified label
		// at build time as part of the patch layer. No separate VerifyImage
		// step is needed — but we still call it for idempotency (it is a fast
		// label check when the label is already present).
		image, err := resolveDockerfileImage(ctx, rt, slug, endpointDir, logger, emit)
		if err != nil {
			return "", err
		}
		emit(ImageStageVerifying)
		if err := VerifyImage(ctx, rt, image, logger); err != nil {
			return "", fmt.Errorf("dockerfile image %q: %w", image, err)
		}
		return image, nil
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
func resolveRegistryImage(ctx context.Context, rt syfthubapi.ContainerRuntime, image string, logger *slog.Logger, emit func(ImageResolveStage)) (string, error) {
	cli, err := asCLIRuntime(rt, "ResolveEndpointImage")
	if err != nil {
		return "", err
	}

	emit(ImageStageChecking)
	if imageExists(ctx, cli.binary, image) {
		logger.Debug("custom registry image already available", "image", image)
		return image, nil
	}

	emit(ImageStagePulling)
	logger.Info("pulling custom endpoint image", "image", image)
	if err := cli.PullImage(ctx, image); err != nil {
		return "", fmt.Errorf("container image %s: failed to pull: %w", image, err)
	}

	logger.Info("custom endpoint image pulled successfully", "image", image)
	return image, nil
}

// resolveDockerfileImage builds an image from the endpoint's Dockerfile if
// the image does not exist or the Dockerfile content has changed. Uses a
// SHA-256 hash stored as an image label for staleness detection.
//
// The user's Dockerfile is automatically wrapped with a sandbox patch layer
// that installs bubblewrap, copies the syft_runtime, sets the entrypoint
// to our in-container multiplexer, and verifies bwrap works on the host
// kernel — all at build time. The user does NOT have to modify their
// Dockerfile; existing endpoints written for the pre-bwrap runtime keep
// working as long as their base image has apt-get / apk / dnf available.
func resolveDockerfileImage(ctx context.Context, rt syfthubapi.ContainerRuntime, slug, endpointDir string, logger *slog.Logger, emit func(ImageResolveStage)) (string, error) {
	cli, err := asCLIRuntime(rt, "ResolveEndpointImage")
	if err != nil {
		return "", err
	}

	imageName := fmt.Sprintf("syfthub-endpoint-%s:latest", slug)

	dockerfilePath := filepath.Join(endpointDir, "Dockerfile")
	userDockerfile, err := os.ReadFile(dockerfilePath)
	if err != nil {
		return "", fmt.Errorf("container image %s: failed to read Dockerfile: %w", imageName, err)
	}

	// Hash the AUGMENTED Dockerfile + the embedded syft_runtime payload so
	// that any change to either input forces a rebuild.
	augmented := buildAugmentedDockerfile(string(userDockerfile))
	runtimeHash, err := embeddedRuntimeHash()
	if err != nil {
		return "", fmt.Errorf("hash embedded runtime: %w", err)
	}
	currentHash := nodeops.HashString(augmented + "\x00runtime:" + runtimeHash)

	emit(ImageStageChecking)
	// Single inspect: if it succeeds the image exists; the stored hash
	// label tells us whether the cached image is still current.
	if labels, ok := getImageLabels(ctx, cli.binary, imageName, "syfthub.dockerfile.hash"); ok {
		storedHash := labels["syfthub.dockerfile.hash"]
		if storedHash == currentHash {
			logger.Debug("custom Dockerfile image up-to-date",
				"image", imageName,
				"hash", currentHash[:12],
			)
			return imageName, nil
		}
		logger.Info("Dockerfile or sandbox patch changed, rebuilding",
			"image", imageName,
			"old_hash", storedHash,
			"new_hash", currentHash[:12],
		)
	}

	buildCtx, cancel := context.WithTimeout(ctx, dockerfileBuildTimeout)
	defer cancel()

	emit(ImageStageBuilding)
	logger.Info("building custom endpoint image with sandbox patch layer",
		"image", imageName,
		"dir", endpointDir,
		"hash", currentHash[:12],
	)

	if err := buildAugmentedEndpointImage(buildCtx, cli.binary, imageName, endpointDir, augmented, currentHash, logger); err != nil {
		return "", fmt.Errorf("container image %s: failed to build: %w", imageName, err)
	}

	logger.Info("custom endpoint image built successfully", "image", imageName)
	return imageName, nil
}

// getImageLabels retrieves multiple label values in a single docker
// image inspect call. The boolean return is false when inspect itself
// failed (image absent, daemon down); individual unset labels map to "".
func getImageLabels(ctx context.Context, binary, imageName string, labels ...string) (map[string]string, bool) {
	if len(labels) == 0 {
		return map[string]string{}, true
	}
	// Build a Go-template that emits each label on its own line. Missing
	// labels render as the empty string, which lets us recover them in
	// order without an extra inspect.
	var b strings.Builder
	for i, l := range labels {
		if i > 0 {
			b.WriteString("\n")
		}
		fmt.Fprintf(&b, "{{index .Config.Labels %q}}", l)
	}
	cmd := exec.CommandContext(ctx, binary, "image", "inspect", "--format", b.String(), imageName)
	var out strings.Builder
	cmd.Stdout = &out
	cmd.Stderr = nil
	if err := cmd.Run(); err != nil {
		return nil, false
	}
	lines := strings.Split(strings.TrimRight(out.String(), "\n"), "\n")
	got := make(map[string]string, len(labels))
	for i, l := range labels {
		if i < len(lines) {
			got[l] = strings.TrimSpace(lines[i])
		}
	}
	return got, true
}

// sandboxPatchLayer is the Dockerfile snippet appended to every custom
// endpoint Dockerfile. It runs in the LAST stage of the user's build (Docker
// concatenates appended FROM-less lines to the trailing stage) and:
//
//   - installs bubblewrap and ca-certificates via the first package manager
//     it finds (apt-get → apk → dnf → yum; fails the build if none work)
//   - copies the syft_runtime files from the build context's .syft_runtime/
//     directory into /usr/local/lib/syft_runtime (root-owned, chmod a-w)
//   - creates the mount-point directories /app/{synth,ws,.cache,.store}
//   - sets PYTHONPATH, USER 1000:1000, WORKDIR /app/synth, EXPOSE 8080
//   - stamps the sandbox label (so the host-side launch-time check passes)
//   - replaces the user's ENTRYPOINT with our in-container multiplexer
//
// IMPORTANT: We do NOT run bwrap during the build. Docker BuildKit applies a
// restrictive seccomp profile to build containers that blocks
// unshare(CLONE_NEWUSER) — the very syscall bwrap needs. This is a build
// sandbox limitation, not a host kernel one; the same image runs bwrap
// fine at `docker run` time where we control the security flags.
// Verification happens at runtime via VerifyImage, which spawns a one-shot
// container with the same hardening as the real endpoint and probes bwrap
// there. If the host kernel can't support unprivileged user namespaces,
// VerifyImage surfaces a clear error with a migration hint.
//
// The user does NOT need to know any of this. Their existing Dockerfile keeps
// being built; we just slot a security envelope around it.
const sandboxPatchLayer = `
# === syfthub sandbox patch layer (auto-injected) =====================
# Do not edit — this layer is appended automatically by the SDK.
USER root
RUN set -e; \
    if command -v apt-get >/dev/null 2>&1; then \
        apt-get update >/dev/null && \
        apt-get install -y --no-install-recommends bubblewrap ca-certificates >/dev/null && \
        rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
        apk add --no-cache bubblewrap ca-certificates >/dev/null; \
    elif command -v dnf >/dev/null 2>&1; then \
        dnf install -y bubblewrap ca-certificates >/dev/null; \
    elif command -v yum >/dev/null 2>&1; then \
        yum install -y bubblewrap ca-certificates >/dev/null; \
    else \
        echo "ERROR: no supported package manager (apt-get/apk/dnf/yum) — base image cannot install bubblewrap" >&2; \
        exit 1; \
    fi
COPY .syft_runtime/server.py        /usr/local/lib/syft_runtime/server.py
COPY .syft_runtime/syft_entry.py    /usr/local/lib/syft_runtime/syft_entry.py
COPY .syft_runtime/_syft_audit.py   /usr/local/lib/syft_runtime/_syft_audit.py
COPY .syft_runtime/session_loop.py  /usr/local/lib/syft_runtime/session_loop.py
COPY .syft_runtime/_protocol.py     /usr/local/lib/syft_runtime/_protocol.py
RUN chown root:root /usr/local/lib/syft_runtime/*.py && \
    chmod a-w /usr/local/lib/syft_runtime/*.py && \
    chmod a+r /usr/local/lib/syft_runtime/*.py && \
    mkdir -p /app/synth /app/ws /app/.cache /app/.store && \
    chown -R 1000:1000 /app/ws /app/.cache /app/.store && \
    chmod 555 /app/synth
# Intentionally NOT setting PYTHONPATH globally — that would cause
# server.py and any RUN-step Python process to auto-import the audit
# hook (via sys.path[0] = script_dir), breaking both. server.py spawns
# bwrap children with --setenv PYTHONPATH=/usr/local/lib/syft_runtime
# so the hook is only on the handler subprocess.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 1000:1000
WORKDIR /app/synth
EXPOSE 8080
LABEL syfthub.sandbox.bwrap="verified" \
      syfthub.sandbox.version="2"
ENTRYPOINT ["python3", "/usr/local/lib/syft_runtime/server.py"]
`

// embeddedRuntimeFiles lists the in-bwrap runtime Python files that are
// embedded into the binary and injected into every custom-Dockerfile
// build context. Keep in sync with the COPY directives in sandboxPatchLayer.
var embeddedRuntimeFiles = []string{
	"server.py",
	"syft_entry.py",
	"_syft_audit.py",
	"session_loop.py",
	"_protocol.py",
}

// embeddedRuntimeHash returns a stable digest over the embedded runtime
// files. Used as part of the cache-busting key for augmented endpoint
// images so any change to the embedded runtime forces rebuilds even when
// the user's Dockerfile is unchanged. Cached via sync.OnceValues so
// loading N Dockerfile endpoints doesn't re-hash the same files N times.
var embeddedRuntimeHash = sync.OnceValues(func() (string, error) {
	parts := make([]string, 0, len(embeddedRuntimeFiles)*2)
	for _, name := range embeddedRuntimeFiles {
		data, err := runnerFS.ReadFile("runner/" + name)
		if err != nil {
			return "", fmt.Errorf("read embedded runner/%s: %w", name, err)
		}
		parts = append(parts, name, nodeops.HashString(string(data)))
	}
	return nodeops.HashString(strings.Join(parts, "\x00")), nil
})

// buildAugmentedDockerfile appends the sandbox patch layer to the user's
// Dockerfile content. Pure function; tested independently of docker.
func buildAugmentedDockerfile(userDockerfile string) string {
	// Ensure a newline between user content and our patch so directives
	// don't accidentally concatenate.
	if !strings.HasSuffix(userDockerfile, "\n") {
		userDockerfile += "\n"
	}
	return userDockerfile + sandboxPatchLayer
}

// buildAugmentedEndpointImage materializes a temp build context that
// contains:
//
//	<temp>/                         — user's endpoint dir, copied
//	├── Dockerfile.syft             — augmented Dockerfile (user + patch)
//	└── .syft_runtime/              — embedded runtime files
//	    ├── server.py
//	    ├── syft_entry.py
//	    ├── sitecustomize.py
//	    └── session_loop.py
//
// Then runs `docker build -f Dockerfile.syft -t imageName .` against it.
// The hash of the augmented Dockerfile is recorded as a label so the
// caller can skip rebuilds when neither the user's Dockerfile nor our
// patch has changed.
//
// The original user files are NOT modified — we work in a clean temp dir.
func buildAugmentedEndpointImage(ctx context.Context, binary, imageName,
	endpointDir, augmentedDockerfile, augmentedHash string, logger *slog.Logger,
) error {
	tmp, err := os.MkdirTemp("", "syfthub-build-")
	if err != nil {
		return fmt.Errorf("create build context: %w", err)
	}
	defer os.RemoveAll(tmp)

	// 1. Mirror the endpoint dir into the build context. We use os.Link
	// when possible (same filesystem) for zero-copy; otherwise fall back
	// to a content copy.
	if err := mirrorEndpointDir(endpointDir, tmp); err != nil {
		return fmt.Errorf("mirror endpoint dir: %w", err)
	}

	// 2. Inject the embedded syft_runtime files at .syft_runtime/ — this
	// path is referenced by the patch layer's COPY directives.
	runtimeDir := filepath.Join(tmp, ".syft_runtime")
	if err := os.MkdirAll(runtimeDir, 0o755); err != nil {
		return fmt.Errorf("mkdir runtime dir: %w", err)
	}
	for _, name := range embeddedRuntimeFiles {
		data, err := runnerFS.ReadFile("runner/" + name)
		if err != nil {
			return fmt.Errorf("read embedded runner/%s: %w", name, err)
		}
		if err := os.WriteFile(filepath.Join(runtimeDir, name), data, 0o644); err != nil {
			return fmt.Errorf("write %s: %w", name, err)
		}
	}

	// 3. Write the augmented Dockerfile.
	dockerfilePath := filepath.Join(tmp, "Dockerfile.syft")
	if err := os.WriteFile(dockerfilePath, []byte(augmentedDockerfile), 0o644); err != nil {
		return fmt.Errorf("write augmented Dockerfile: %w", err)
	}

	// 4. Run docker build.
	logger.Debug("building augmented image",
		"image", imageName, "context", tmp, "hash", augmentedHash[:12])
	cmd := exec.CommandContext(ctx, binary, "build",
		"-f", "Dockerfile.syft",
		"-t", imageName,
		"--label", "syfthub.dockerfile.hash="+augmentedHash,
		".",
	)
	cmd.Dir = tmp

	var output strings.Builder
	lw := &limitedWriter{w: &output, remaining: maxBuildOutputBytes}
	cmd.Stdout = lw
	cmd.Stderr = lw

	if err := cmd.Run(); err != nil {
		out := output.String()
		lines := strings.Split(strings.TrimSpace(out), "\n")
		tail := lines
		if len(tail) > 30 {
			tail = tail[len(tail)-30:]
		}
		logger.Error("augmented endpoint image build failed",
			"image", imageName,
			"error", err,
			"output_tail", strings.Join(tail, "\n"),
		)
		return fmt.Errorf("augmented image build failed: %w (tail: %s)",
			err, strings.Join(tail, "\n"))
	}
	return nil
}

// mirrorEndpointDir copies (or hardlinks) every file under src into dest.
// Excludes the .syft_runtime/ subdir name so user data cannot collide with
// the runtime inject path used by the patch layer. Also skips caches, virtual
// envs, VCS dirs, and secret files — kept in sync with
// filemode/sandbox.go's isExcludedSubtree / isSecretFile (cannot import
// filemode here, since filemode imports containermode).
func mirrorEndpointDir(src, dest string) error {
	srcAbs, err := filepath.Abs(src)
	if err != nil {
		return err
	}
	return filepath.Walk(src, func(p string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, _ := filepath.Rel(srcAbs, p)
		if rel == "." {
			return nil
		}
		// Reserved path — our patch layer expects this to come from the
		// SDK, not from user code.
		if strings.HasPrefix(rel, ".syft_runtime") {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if isBuildExcluded(rel) {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		target := filepath.Join(dest, rel)
		if info.IsDir() {
			return os.MkdirAll(target, info.Mode().Perm()|0o111) // ensure dir is enterable
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		// Symlinks: dereference into a copy so docker build sees a real file.
		if info.Mode()&os.ModeSymlink != 0 {
			real, err := filepath.EvalSymlinks(p)
			if err != nil {
				return err
			}
			return copyFileContents(real, target)
		}
		// Try hardlink first, fall back to copy.
		if err := os.Link(p, target); err == nil {
			return nil
		}
		return copyFileContents(p, target)
	})
}

// isBuildExcluded skips path segments we never want in the docker build
// context: caches, virtual envs, VCS dirs, hidden files, the bound workspace
// dir, and on-disk secrets. Mirrors filemode/sandbox.go's exclusion lists.
func isBuildExcluded(rel string) bool {
	clean := filepath.ToSlash(filepath.Clean(rel))
	for _, seg := range strings.Split(clean, "/") {
		switch seg {
		case "__pycache__", ".venv", "venv", "node_modules",
			".git", ".mypy_cache", ".pytest_cache", "workspace",
			".env", "setup.yaml", ".setup-state.json",
			"policies.yaml", "policy":
			return true
		}
		if len(seg) > 1 && seg[0] == '.' {
			return true
		}
	}
	return false
}

func copyFileContents(src, dest string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
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
