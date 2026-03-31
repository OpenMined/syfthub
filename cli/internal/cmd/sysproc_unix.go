//go:build !windows

package cmd

import (
	"os/exec"
	"syscall"
)

// setDaemonSysProcAttr configures the command to run in a new session
// so the daemon is not killed when the parent terminal exits.
func setDaemonSysProcAttr(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
}
