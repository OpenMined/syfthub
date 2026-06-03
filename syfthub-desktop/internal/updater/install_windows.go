//go:build windows

package updater

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"syscall"
)

func inPlaceSupported() bool { return true }

// swapAndRelaunch on Windows:
//   - rename exePath → exePath+".old.exe" (Windows allows renaming an
//     in-use .exe via MoveFileEx, which os.Rename uses under the hood).
//   - copy newBinaryPath to exePath.
//
// Windows does not permit deleting an open .exe; the .old.exe leftover
// is cleaned up on the next launch's --post-update step.
func swapAndRelaunch(exePath, newBinaryPath string) error {
	oldPath := exePath + ".old.exe"

	// If a previous failed install left an .old.exe, clear it first —
	// otherwise Rename can fail.
	_ = os.Remove(oldPath)

	if err := os.Rename(exePath, oldPath); err != nil {
		return fmt.Errorf("rename current to .old.exe: %w", err)
	}

	if err := copyFile(newBinaryPath, exePath); err != nil {
		// Try to undo the rename.
		_ = os.Rename(oldPath, exePath)
		return fmt.Errorf("copy new binary: %w", err)
	}
	return nil
}

func copyFile(src, dst string) error {
	sf, err := os.Open(src)
	if err != nil {
		return err
	}
	defer sf.Close()
	df, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o755)
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

// startDetached on Windows uses CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS
// so the child survives the parent's exit and doesn't inherit our console.
func startDetached(cmd *exec.Cmd) error {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		// 0x00000008 = DETACHED_PROCESS, 0x00000200 = CREATE_NEW_PROCESS_GROUP
		CreationFlags: 0x00000008 | 0x00000200,
	}
	return cmd.Start()
}

// relaunch starts the freshly swapped binary detached, forwarding the
// post-update cleanup flag.
func relaunch(exePath string) error {
	cmd := exec.Command(exePath, PostUpdateFlag)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = nil, nil, nil
	return startDetached(cmd)
}

// cleanupPlatformArtifact is a no-op on Windows — the generic
// PostUpdateCleanup already removes the sibling ".old.exe" binary.
func cleanupPlatformArtifact(string) {}

// rollbackPlatformArtifact returns handled=false on Windows so
// PerformRollback uses its generic ".old.exe" restore logic.
func rollbackPlatformArtifact(string) (string, bool, error) { return "", false, nil }
