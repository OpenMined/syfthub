package updater

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync/atomic"
	"time"
)

// InstallStage describes the state of an in-flight install.
type InstallStage string

const (
	InstallIdle      InstallStage = "idle"
	InstallPreparing InstallStage = "preparing"
	InstallSwapping  InstallStage = "swapping"
	InstallRestart   InstallStage = "restarting"
	InstallFailed    InstallStage = "failed"
)

// InstallState is emitted on the "update:install" event.
type InstallState struct {
	Stage   InstallStage `json:"stage"`
	Version string       `json:"version,omitempty"`
	Step    string       `json:"step,omitempty"` // free-form, e.g. "stopping node daemon"
	Error   string       `json:"error,omitempty"`
}

// InstallEmitter publishes install-progress events to the frontend.
type InstallEmitter interface {
	EmitInstall(state InstallState)
}

// DrainFunc is called before the binary swap. It MUST stop the node
// daemon, end agent sessions, close NATS, and flush state. Errors are
// fatal to the install — we'd rather abort than leave a half-drained
// app running on an unswapped binary.
type DrainFunc func(ctx context.Context) error

// Quitter is the post-swap relaunch shutdown hook. The implementation
// invokes the Wails runtime.Quit so the app exits cleanly after the
// new process has been spawned.
type Quitter interface {
	Quit()
}

// PostUpdateFlag is the CLI flag the post-update binary inspects on first
// launch to perform cleanup (delete sibling .old binaries).
const PostUpdateFlag = "--post-update"

// LaunchStateFileName is the filename (under the caller-provided dir)
// of the rollback bookkeeping file.
const LaunchStateFileName = "launch-state.json"

// MinCleanBootSeconds is how long after OnDomReady the app must run
// before being considered a successful boot for rollback purposes.
const MinCleanBootSeconds = 30

// MaxBootAttempts is the threshold of failed boots after an install
// that triggers a rollback.
const MaxBootAttempts = 3

// errors
var (
	ErrInstallInProgress    = errors.New("an install is already in progress")
	ErrNoDownloadedArtifact = errors.New("no downloaded artifact for the current version")
	ErrUnsupportedPlatform  = errors.New("in-place install is not supported on this platform yet")
)

// Installer orchestrates the binary swap. It is OS-agnostic at this
// layer; the actual rename/relaunch lives in install_<os>.go behind
// the swapAndRelaunch function.
type Installer struct {
	emitter   InstallEmitter
	logger    Logger
	launchDir string

	inFlight atomic.Bool
}

func NewInstaller(launchStateDir string, emitter InstallEmitter, logger Logger) *Installer {
	if logger == nil {
		logger = nopLogger{}
	}
	return &Installer{
		emitter:   emitter,
		logger:    logger,
		launchDir: launchStateDir,
	}
}

// Install performs the full install dance: verify hash, drain, swap,
// record launch state, spawn new process, quit. The artifact at
// downloadedPath must already be SHA-256-verified by the downloader;
// Install re-checks defensively before swapping.
//
// On success this function does not return — the running process exits
// via the Quitter. Errors mean the swap did not happen.
func (i *Installer) Install(
	ctx context.Context,
	version string,
	downloadedPath string,
	expectedSHA256 string,
	drain DrainFunc,
	quit Quitter,
) error {
	if !i.inFlight.CompareAndSwap(false, true) {
		return ErrInstallInProgress
	}
	// We intentionally do NOT release inFlight on success — the process
	// is about to exit. Released only on the error paths below.

	emit := func(s InstallStage, step string, err error) {
		st := InstallState{Stage: s, Version: version, Step: step}
		if err != nil {
			st.Error = err.Error()
		}
		if i.emitter != nil {
			i.emitter.EmitInstall(st)
		}
	}

	fail := func(step string, err error) error {
		i.inFlight.Store(false)
		i.logger.Error(fmt.Sprintf("install failed at %s: %v", step, err))
		emit(InstallFailed, step, err)
		return err
	}

	// Step 0: pre-flight checks.
	if downloadedPath == "" {
		return fail("preflight", ErrNoDownloadedArtifact)
	}
	if !inPlaceSupported() {
		return fail("preflight", ErrUnsupportedPlatform)
	}

	// Step 1: verify hash one more time.
	emit(InstallPreparing, "verifying download", nil)
	if got, err := hashFile(downloadedPath); err != nil {
		return fail("hash artifact", err)
	} else if got != expectedSHA256 {
		return fail("hash artifact", ErrChecksumMismatch)
	}

	// Step 2: drain the running app.
	emit(InstallPreparing, "stopping background work", nil)
	if drain != nil {
		drainCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		if err := drain(drainCtx); err != nil {
			cancel()
			return fail("drain", err)
		}
		cancel()
	}

	// Step 3: record install-time bookkeeping (BEFORE the swap so the
	// post-update process can find it).
	exePath, err := os.Executable()
	if err != nil {
		return fail("locate executable", err)
	}
	if err := writeLaunchState(i.launchDir, launchState{
		LastInstallVersion: version,
		InstallTime:        time.Now().UTC(),
		BootAttempts:       0,
	}); err != nil {
		return fail("write launch state", err)
	}

	// Step 4: swap the running binary.
	emit(InstallSwapping, "replacing binary", nil)
	if err := swapAndRelaunch(exePath, downloadedPath); err != nil {
		return fail("swap binary", err)
	}

	// Step 5: relaunch the new binary. The relaunch mechanism is
	// platform-specific (a detached exec on Linux/Windows, `open -n` of
	// the .app bundle on macOS) and lives behind the relaunch hook.
	emit(InstallRestart, "launching new version", nil)
	if err := relaunch(exePath); err != nil {
		return fail("start new process", err)
	}

	// Step 6: exit current process. The Quitter triggers Wails's
	// OnShutdown so any final cleanup the App layer needs (logging,
	// state flush) gets a chance to run.
	if quit != nil {
		quit.Quit()
	} else {
		os.Exit(0)
	}
	return nil
}

// PostUpdateCleanup deletes the leftover from a recent install. On
// Linux/Windows that's the sibling .old / .old.exe binary; on macOS the
// platform hook removes the moved-aside .app.old bundle. Called from
// main.go when the --post-update flag is present.
func PostUpdateCleanup(exePath string) {
	candidates := []string{
		exePath + ".old",
		exePath + ".old.exe",
	}
	if filepath.Ext(exePath) == ".exe" {
		base := exePath[:len(exePath)-len(".exe")]
		candidates = append(candidates, base+".old.exe", base+".old")
	}
	for _, p := range candidates {
		if p == exePath {
			continue
		}
		_ = os.Remove(p)
	}
	// Bundle-granularity cleanup (macOS); no-op elsewhere.
	cleanupPlatformArtifact(exePath)
}
