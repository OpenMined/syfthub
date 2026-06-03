//go:build linux

package updater

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"syscall"
)

func inPlaceSupported() bool { return true }

// swapAndRelaunch on Linux:
//   - rename exePath → exePath+".old" (preserves the inode so the running
//     mapping stays valid)
//   - copy newBinaryPath to exePath with 0o755 mode
//   - sync to disk
//
// We do NOT delete .old here — the post-update process does that on its
// first clean boot, leaving a fallback path if the new binary doesn't
// start.
func swapAndRelaunch(exePath, newBinaryPath string) error {
	oldPath := exePath + ".old"

	// Move the running binary aside. On Linux this works even while the
	// process is executing.
	if err := os.Rename(exePath, oldPath); err != nil {
		return fmt.Errorf("rename current to .old: %w", err)
	}

	// Copy new binary into the original name.
	if err := copyFileMode(newBinaryPath, exePath, 0o755); err != nil {
		// Best-effort recovery: try to put the old binary back.
		_ = os.Rename(oldPath, exePath)
		return fmt.Errorf("copy new binary: %w", err)
	}
	return nil
}

func copyFileMode(src, dst string, mode os.FileMode) error {
	sf, err := os.Open(src)
	if err != nil {
		return err
	}
	defer sf.Close()
	df, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, mode)
	if err != nil {
		return err
	}
	if _, err := io.Copy(df, sf); err != nil {
		df.Close()
		return err
	}
	if err := df.Sync(); err != nil {
		df.Close()
		return err
	}
	return df.Close()
}

func startDetached(cmd *exec.Cmd) error {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	return cmd.Start()
}

// relaunch starts the freshly swapped binary detached, forwarding the
// post-update cleanup flag.
func relaunch(exePath string) error {
	cmd := exec.Command(exePath, PostUpdateFlag)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = nil, nil, nil
	return startDetached(cmd)
}

// cleanupPlatformArtifact is a no-op on Linux — the generic
// PostUpdateCleanup already removes the sibling ".old" binary.
func cleanupPlatformArtifact(string) {}

// rollbackPlatformArtifact returns handled=false on Linux so
// PerformRollback uses its generic ".old" restore logic.
func rollbackPlatformArtifact(string) (string, bool, error) { return "", false, nil }
