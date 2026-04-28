package cmd

import (
	"os"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var nodeStopJSON bool

var nodeStopCmd = &cobra.Command{
	Use:         "stop",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "Stop a running node",
	Long:        `Stop a running SyftHub node by sending SIGTERM to its process.`,
	RunE:        runNodeStop,
}

func init() {
	nodeStopCmd.Flags().BoolVar(&nodeStopJSON, "json", false, "Output result as JSON")
}

func runNodeStop(cmd *cobra.Command, args []string) error {
	pid, err := nodeconfig.ReadPID()
	if err != nil {
		output.ReplyErrorSoft(nodeStopJSON, "No running node found.")
		return nil
	}

	proc, err := os.FindProcess(pid)
	if err != nil {
		nodeconfig.RemovePID()
		output.ReplyErrorSoft(nodeStopJSON, "Process %d not found.", pid)
		return nil
	}

	// Check if process is actually running
	if err := proc.Signal(syscall.Signal(0)); err != nil {
		nodeconfig.RemovePID()
		msg := "Node is not running (stale PID file removed)."
		if nodeStopJSON {
			output.JSON(map[string]any{"status": output.StatusError, "message": msg})
		} else {
			output.Warning(msg)
		}
		return nil
	}

	// Send SIGTERM
	if err := proc.Signal(syscall.SIGTERM); err != nil {
		return output.ReplyError(nodeStopJSON, "Failed to stop node: %v", err)
	}

	// Wait for process to exit (up to 5 seconds)
	stopped := false
	for i := 0; i < 10; i++ {
		time.Sleep(500 * time.Millisecond)
		if err := proc.Signal(syscall.Signal(0)); err != nil {
			stopped = true
			break
		}
	}

	nodeconfig.RemovePID()

	if stopped {
		if nodeStopJSON {
			output.JSON(map[string]any{"status": output.StatusSuccess, "message": "Node stopped.", "pid": pid})
		} else {
			output.Success("Node stopped (PID %d).", pid)
		}
	} else {
		if nodeStopJSON {
			output.JSON(map[string]any{"status": "warning", "message": "SIGTERM sent but process may still be running.", "pid": pid})
		} else {
			output.Warning("SIGTERM sent to PID %d but process may still be running.", pid)
		}
	}

	return nil
}
