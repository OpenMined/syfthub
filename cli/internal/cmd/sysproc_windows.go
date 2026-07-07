//go:build windows

package cmd

import (
	"os/exec"
	"syscall"
)

// setDaemonSysProcAttr configures the command to run detached from the
// parent console so the daemon survives after the terminal exits.
func setDaemonSysProcAttr(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP,
	}
}
