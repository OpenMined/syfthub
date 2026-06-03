//go:build darwin

package updater

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// inPlaceSupported reports whether the updater can replace the running
// app in place. Enabled on macOS now that release builds are
// Developer-ID signed and notarized (release-desktop.yml,
// build-macos-arm64): a downloaded .app launches without a Gatekeeper
// prompt, so the assisted-download / manual-install fallback is gone.
func inPlaceSupported() bool { return true }

// appBundleRoot walks up from the running executable to the enclosing
// .app bundle directory, e.g.
//
//	/Applications/SyftHub Desktop.app/Contents/MacOS/syfthub-desktop
//	→ /Applications/SyftHub Desktop.app
//
// Returns "" when exePath is not inside a .app bundle (e.g. a bare binary
// from a dev build), in which case in-place install is impossible.
func appBundleRoot(exePath string) string {
	dir := filepath.Dir(exePath)
	for {
		if strings.HasSuffix(dir, ".app") {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return ""
		}
		dir = parent
	}
}

// swapAndRelaunch on macOS replaces the entire .app bundle.
//
// Unlike Linux/Windows — where the downloaded artifact is a bare binary
// renamed over the running one — the macOS artifact is a .zip produced by
// `ditto` containing the signed .app. We extract it with `ditto` (NOT
// archive/zip) so the bundle's extended attributes and code signature
// survive: a signature broken by a naive unzip would be rejected by
// Gatekeeper and fail to launch.
//
// The swap is a directory rename at bundle granularity, mirroring the
// Linux ".old" dance — the running process keeps executing from the
// moved-aside bundle while the new one takes the original path.
func swapAndRelaunch(exePath, zipPath string) error {
	bundle := appBundleRoot(exePath)
	if bundle == "" {
		return fmt.Errorf("locate .app bundle from %q: %w", exePath, ErrUnsupportedPlatform)
	}
	parent := filepath.Dir(bundle)

	// Extract into a temp dir on the SAME volume as the bundle so the
	// final move-into-place is an atomic rename, not a cross-device copy.
	staging, err := os.MkdirTemp(parent, ".syfthub-update-")
	if err != nil {
		return fmt.Errorf("create staging dir: %w", err)
	}
	defer os.RemoveAll(staging)

	if out, err := exec.Command("/usr/bin/ditto", "-x", "-k", zipPath, staging).CombinedOutput(); err != nil {
		return fmt.Errorf("ditto extract: %v: %s", err, strings.TrimSpace(string(out)))
	}

	newApp, err := findAppBundle(staging)
	if err != nil {
		return err
	}

	oldPath := bundle + ".old"
	_ = os.RemoveAll(oldPath) // clear any stale bundle from a prior install

	// Move the running bundle aside. The executing process is unaffected —
	// macOS keeps the open vnode valid across the rename.
	if err := os.Rename(bundle, oldPath); err != nil {
		return fmt.Errorf("move current bundle aside: %w", err)
	}
	// Move the new bundle into the canonical location.
	if err := os.Rename(newApp, bundle); err != nil {
		_ = os.Rename(oldPath, bundle) // best-effort recovery
		return fmt.Errorf("install new bundle: %w", err)
	}
	return nil
}

// findAppBundle returns the single top-level *.app directory inside dir.
// ditto archives created with --keepParent unpack to exactly one .app at
// the root; any __MACOSX sibling is ignored.
func findAppBundle(dir string) (string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", fmt.Errorf("read staging dir: %w", err)
	}
	for _, e := range entries {
		if e.IsDir() && strings.HasSuffix(e.Name(), ".app") {
			return filepath.Join(dir, e.Name()), nil
		}
	}
	return "", errors.New("no .app bundle found in downloaded archive")
}

// relaunch starts the freshly installed app. On macOS we launch the
// bundle via `open -n` rather than exec'ing the inner Mach-O directly so
// LaunchServices registers the new instance correctly (Dock placement,
// activation, and the bundle's signed identity). The --post-update flag
// is forwarded so the new process cleans up the .old bundle on first boot.
func relaunch(exePath string) error {
	if bundle := appBundleRoot(exePath); bundle != "" {
		cmd := exec.Command("/usr/bin/open", "-n", bundle, "--args", PostUpdateFlag)
		cmd.Stdin, cmd.Stdout, cmd.Stderr = nil, nil, nil
		return startDetached(cmd)
	}
	// Fallback for a bare binary (shouldn't happen — swapAndRelaunch
	// would have already failed without a bundle).
	cmd := exec.Command(exePath, PostUpdateFlag)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = nil, nil, nil
	return startDetached(cmd)
}

// cleanupPlatformArtifact removes the moved-aside bundle from the last
// install (and any .bad bundle left by a rollback). Called on first
// launch of the new version via --post-update.
func cleanupPlatformArtifact(exePath string) {
	if bundle := appBundleRoot(exePath); bundle != "" {
		_ = os.RemoveAll(bundle + ".old")
		_ = os.RemoveAll(bundle + ".bad")
	}
}

// rollbackPlatformArtifact restores the previous .app bundle when the
// freshly installed version fails to boot repeatedly. handled is always
// true on macOS — rollback operates on the bundle, never the bare
// ".old" binary the generic path looks for. Returns the inner executable
// to exec for the restored bundle.
func rollbackPlatformArtifact(exePath string) (restored string, handled bool, err error) {
	bundle := appBundleRoot(exePath)
	if bundle == "" {
		return "", true, errors.New("cannot locate .app bundle for rollback")
	}
	oldPath := bundle + ".old"
	if _, statErr := os.Stat(oldPath); statErr != nil {
		return "", true, errors.New("no rollback bundle found")
	}
	badPath := bundle + ".bad"
	_ = os.RemoveAll(badPath)
	if err := os.Rename(bundle, badPath); err != nil {
		return "", true, fmt.Errorf("move bad bundle aside: %w", err)
	}
	if err := os.Rename(oldPath, bundle); err != nil {
		_ = os.Rename(badPath, bundle) // undo
		return "", true, fmt.Errorf("restore .old bundle: %w", err)
	}
	return exePath, true, nil
}

func startDetached(cmd *exec.Cmd) error {
	return cmd.Start()
}
