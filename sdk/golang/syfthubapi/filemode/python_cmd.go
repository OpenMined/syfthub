package filemode

import (
	"bytes"
	"context"
	"os/exec"
)

// maxStdoutBytes caps the in-memory buffer for a Python handler's stdout.
// 16 MiB is generous for JSON payloads (executor) yet still bounded so a
// runaway handler cannot OOM the host process.
const maxStdoutBytes = 1 << 24 // 16 MiB

// newPythonCmd builds an *exec.Cmd for python with the standard env + workdir
// + Windows console hiding applied. baseEnv is the cached os.Environ snapshot
// from constructor time; env is the endpoint-specific overlay appended on top.
//
// Both SubprocessExecutor and the agent handler share this so the subprocess
// setup (PATH inheritance, endpoint env vars, hidden console window on
// Windows) cannot drift between the two call sites.
func newPythonCmd(ctx context.Context, pythonPath string, args []string, workDir string, baseEnv, env []string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, pythonPath, args...)
	cmd.Dir = workDir
	// Allocate a fresh slice so we never mutate the caller's baseEnv snapshot.
	combined := make([]string, 0, len(baseEnv)+len(env))
	combined = append(combined, baseEnv...)
	combined = append(combined, env...)
	cmd.Env = combined
	hideWindow(cmd)
	return cmd
}

// limitedBuffer is a bytes.Buffer that silently discards writes once a fixed
// capacity is reached. Used to cap subprocess stdout so a misbehaving Python
// handler cannot exhaust process memory by streaming output without flushing.
//
// The Write method always reports the full length of p as written so that
// callers (notably os/exec when wiring cmd.Stdout) do not see a short-write
// error after the cap is hit.
//
// This mirrors the limitedWriter idiom used by containermode/image.go for
// docker build output capture, kept package-private here because filemode
// captures into a bytes.Buffer (for downstream JSON parsing) while containermode
// captures into a strings.Builder (for log diagnostics only).
type limitedBuffer struct {
	bytes.Buffer
	cap int
}

// Write appends up to (cap - current length) bytes from p to the underlying
// buffer and silently discards the rest. It always returns the original
// len(p), nil on success so that exec.Cmd does not error with "short write".
func (lb *limitedBuffer) Write(p []byte) (int, error) {
	original := len(p)
	remaining := lb.cap - lb.Buffer.Len()
	if remaining <= 0 {
		return original, nil
	}
	if len(p) > remaining {
		p = p[:remaining]
	}
	if _, err := lb.Buffer.Write(p); err != nil {
		return 0, err
	}
	// Report the original write length (pre-truncation) so callers don't
	// observe a short write. The discarded tail is intentional.
	return original, nil
}
