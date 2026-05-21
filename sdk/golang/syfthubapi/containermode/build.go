// Package containermode — build.go: image verification.
//
// Any image that wants to be used as a SyftHub endpoint runner must satisfy
// two contracts:
//
//  1. bwrap is installed and works (user namespaces available on this host).
//  2. /usr/local/lib/syft_runtime/{sitecustomize,syft_entry,session_loop}.py
//     are present and importable.
//
// VerifyImage spawns a one-shot container that runs the embedded probe.sh
// script and checks the exit code. On success it stamps the image with a
// pair of labels (syfthub.sandbox.bwrap=verified, syfthub.sandbox.version=1)
// that NewContainerExecutor reads at launch time to refuse unverified images.
//
// For the default image, the Dockerfile RUN bwrap …` step already executes
// during `docker build`, so the label is set at build time. VerifyImage is
// the gate for CUSTOM endpoint Dockerfiles where we cannot trust the author
// to have verified bwrap themselves.

package containermode

import (
	"context"
	_ "embed"
	"errors"
	"fmt"
	"log/slog"
	"os/exec"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// sandboxLabelKey is the OCI image label that asserts the image passed
// VerifyImage (or was built from a Dockerfile whose RUN bwrap step
// verified it at build time). NewContainerExecutor refuses to launch an
// image without this label set to "verified".
const sandboxLabelKey = "syfthub.sandbox.bwrap"

// sandboxLabelValue is the constant the host SDK requires to see in the
// label. Future runtime versions may bump this; old labels will fail
// validation and force a rebuild.
const sandboxLabelValue = "verified"

// sandboxVersionLabelKey is the in-container runtime version. Bumped
// whenever the in-container contract changes (Python files, IPC shape,
// audit hook policy). NewContainerExecutor accepts only versions in
// AcceptedSandboxVersions.
const sandboxVersionLabelKey = "syfthub.sandbox.version"

// AcceptedSandboxVersions is the set of in-container runtime versions
// the host SDK can talk to. Bump on breaking-protocol changes.
//
//	"1" — initial layout; placed audit hook in sitecustomize.py and set
//	      PYTHONPATH globally. Caused server.py and apt-get python
//	      post-install scripts to be incorrectly audited.
//	"2" — audit hook renamed to _syft_audit.py, imported explicitly by
//	      syft_entry.py; PYTHONPATH no longer set as a container ENV.
//
// Including only the current version forces a host-side relaunch refusal
// for any cached image stamped with an older version → the augmented
// build runs again and produces a v2 image.
var AcceptedSandboxVersions = map[string]struct{}{
	"2": {},
}

// currentSandboxVersion is the version stamped on freshly-built or
// freshly-verified images. Keep in sync with the LABEL in the default
// Dockerfile and in sandboxPatchLayer.
const currentSandboxVersion = "2"

//go:embed runner/probe.sh
var probeScript []byte

// ProbeTimeout caps how long the verification probe is allowed to run.
// 15 seconds is plenty for bwrap to spin up two namespaces and exit.
const ProbeTimeout = 15 * time.Second

// ErrImageNotVerified is returned by NewContainerExecutor (and the
// front-door VerifyImage call) when an image does not carry the
// syfthub.sandbox.bwrap=verified label.
var ErrImageNotVerified = errors.New("image is not bwrap-verified — refuse to launch")

// VerifyImage runs the embedded probe script inside a one-shot container
// built from imageName, using the same hardening flags the real endpoint
// container will use, and stamps the verified label on success.
//
// Idempotent: if the image already carries syfthub.sandbox.bwrap=verified
// AND its sandbox.version is accepted, returns nil immediately.
func VerifyImage(ctx context.Context, rt syfthubapi.ContainerRuntime,
	imageName string, logger *slog.Logger,
) error {
	cli, err := asCLIRuntime(rt, "VerifyImage")
	if err != nil {
		return err
	}

	// Already verified? Skip the probe.
	if HasSandboxLabel(ctx, cli.binary, imageName) {
		logger.Debug("image already verified", "image", imageName)
		return nil
	}

	logger.Info("running bwrap verification probe", "image", imageName)

	probeCtx, cancel := context.WithTimeout(ctx, ProbeTimeout)
	defer cancel()

	// We embed probe.sh and pipe it into `sh -s` via the container's
	// stdin. Avoids needing to ship the probe inside every custom image
	// — the contract is "your image has /bin/sh + bwrap + the runtime".
	//
	// `--entrypoint /bin/sh` is required because `docker run image cmd`
	// APPENDS cmd to the image's ENTRYPOINT, it does not replace it. If
	// the user's custom Dockerfile inherits an entrypoint (e.g., from an
	// older syfthub base image), `/bin/sh -s` would get fed as argparse
	// arguments to that entrypoint instead of running the probe.
	args := []string{
		"run",
		"--rm",
		"--network", "none",
		"--read-only",
		"--user", "1000:1000",
		"--cap-drop", "ALL",
		"--security-opt", "no-new-privileges",
		// Match BuildEndpointSpec so the probe runs under exactly the
		// same kernel-visible constraints the real endpoint container
		// will use. Without seccomp=unconfined, bwrap can't create user
		// namespaces (Docker default seccomp blocks unshare). Without
		// apparmor=unconfined, bwrap can't set up its mount namespace
		// (docker-default AppArmor blocks mount --make-slave).
		"--security-opt", "seccomp=unconfined",
		"--security-opt", "apparmor=unconfined",
		"--tmpfs", "/tmp",
		"--entrypoint", "/bin/sh",
		"-i", // stdin open
		imageName,
		"-s",
	}
	cmd := exec.CommandContext(probeCtx, cli.binary, args...)
	cmd.Stdin = strings.NewReader(string(probeScript))

	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		hint := verificationHint(err, stderr.String())
		logger.Error("verification probe failed",
			"image", imageName,
			"error", err,
			"stdout", trimTail(stdout.String(), 400),
			"stderr", trimTail(stderr.String(), 400),
			"hint", hint,
		)
		return fmt.Errorf("image %q failed bwrap verification: %w\n  stderr: %s\n  hint: %s",
			imageName, err,
			trimTail(stderr.String(), 400),
			hint,
		)
	}

	// Stamp the verified label so future launches skip the probe.
	if err := stampSandboxLabel(probeCtx, cli.binary, imageName, logger); err != nil {
		return fmt.Errorf("verified but could not stamp label: %w", err)
	}

	logger.Info("image verified and labeled", "image", imageName)
	return nil
}

// EnsureImageVerified is a launch-time check used by NewContainerExecutor
// to refuse images that have not passed VerifyImage (or that pre-date
// the bwrap-in-container architecture).
//
// Returns ErrImageNotVerified — wrap accordingly to surface a useful
// error to the end user.
func EnsureImageVerified(ctx context.Context, rt syfthubapi.ContainerRuntime,
	imageName string, logger *slog.Logger,
) error {
	cli, err := asCLIRuntime(rt, "EnsureImageVerified")
	if err != nil {
		return err
	}
	if HasSandboxLabel(ctx, cli.binary, imageName) {
		return nil
	}
	logger.Error("image missing sandbox label — refusing to launch",
		"image", imageName,
		"label_required", sandboxLabelKey+"="+sandboxLabelValue,
		"hint", "rebuild with the upstream Dockerfile or call containermode.VerifyImage first",
	)
	return fmt.Errorf("%w: %s (missing label %s=%s)",
		ErrImageNotVerified, imageName, sandboxLabelKey, sandboxLabelValue)
}

// HasSandboxLabel returns true if the image carries the verified label
// AND its sandbox.version is one we accept.
func HasSandboxLabel(ctx context.Context, binary, imageName string) bool {
	labels, ok := getImageLabels(ctx, binary, imageName,
		sandboxLabelKey, sandboxVersionLabelKey)
	if !ok || labels[sandboxLabelKey] != sandboxLabelValue {
		return false
	}
	version := labels[sandboxVersionLabelKey]
	if version == "" {
		// Legacy verified images without a version label fail closed.
		return false
	}
	_, accepted := AcceptedSandboxVersions[version]
	return accepted
}

// stampSandboxLabel applies the verified label to an existing image by
// running `docker image tag` after committing a tiny no-op layer. The
// cheapest equivalent is `docker build` with FROM imageName and a LABEL
// directive — a single trivial layer is added.
func stampSandboxLabel(ctx context.Context, binary, imageName string, logger *slog.Logger) error {
	dockerfile := fmt.Sprintf("FROM %s\nLABEL %s=%s %s=%s\n",
		imageName,
		sandboxLabelKey, sandboxLabelValue,
		sandboxVersionLabelKey, currentSandboxVersion,
	)
	cmd := exec.CommandContext(ctx, binary, "build", "-t", imageName, "-")
	cmd.Stdin = strings.NewReader(dockerfile)

	var out strings.Builder
	cmd.Stdout = &out
	cmd.Stderr = &out
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("docker build (label stamp) failed: %w (output: %s)",
			err, trimTail(out.String(), 400))
	}
	logger.Debug("stamped sandbox label", "image", imageName)
	return nil
}

// trimTail returns the last n characters of s, prefixed with an ellipsis
// when truncation happened.
func trimTail(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return "..." + s[len(s)-n:]
}

// verificationHint maps the probe's exit code (see runner/probe.sh) to a
// short, actionable migration message. Falls back to stderr matching when
// the exit code isn't available (e.g., docker itself failed before the
// probe could run).
func verificationHint(runErr error, stderr string) string {
	exitCode := -1
	var exitErr *exec.ExitError
	if errors.As(runErr, &exitErr) {
		exitCode = exitErr.ExitCode()
	}
	return hintForExitCode(exitCode, stderr)
}

// exitCodeHints maps probe.sh exit codes (see runner/probe.sh) to a
// user-facing migration message.
var exitCodeHints = map[int]string{
	10: "image is missing bubblewrap. Update your Dockerfile to install it " +
		"(apt-get install -y bubblewrap) or rebase on syfthub/endpoint-runner. " +
		"If your Dockerfile already FROMs syfthub/endpoint-runner, your local " +
		"base image may be stale — run `docker rmi syfthub/endpoint-runner:latest` " +
		"and reload the endpoint to pull the new base.",
	11: "the host kernel does not allow unprivileged user namespaces. " +
		"Set `sysctl kernel.unprivileged_userns_clone=1` (Debian) or update " +
		"to a newer kernel where this is enabled by default.",
	12: "image is missing /usr/local/lib/syft_runtime. Rebase on " +
		"syfthub/endpoint-runner or copy server.py/syft_entry.py/" +
		"sitecustomize.py/session_loop.py into that path.",
	13: "image's python3 is too old. Use Python 3.9+ (e.g., python:3.11-slim).",
}

// hintForExitCode is the testable core: given the probe's exit code (or -1
// when not available) and the captured stderr, return the user-facing hint.
func hintForExitCode(exitCode int, stderr string) string {
	if hint, ok := exitCodeHints[exitCode]; ok {
		return hint
	}
	s := strings.ToLower(stderr)
	if strings.Contains(s, "unrecognized arguments") || strings.Contains(s, "container_runner") {
		return "image inherits an older syfthub entrypoint. Your local base image " +
			"is stale — run `docker rmi syfthub/endpoint-runner:latest` and reload."
	}
	return "see stderr above. Refer to docs/architecture/sandbox.md for the " +
		"container contract (bwrap + /usr/local/lib/syft_runtime + Python 3.9+)."
}
