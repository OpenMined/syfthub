package cmd

import (
	"fmt"
	"os"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var nodeStopJSON bool

var nodeStopCmd = &cobra.Command{
	Use:   "stop",
	Short: "Stop a running node",
	Long:  `Stop a running SyftHub node by sending SIGTERM to its process.`,
	RunE:  runNodeStop,
}

func init() {
	nodeStopCmd.Flags().BoolVar(&nodeStopJSON, "json", false, "Output result as JSON")
}

func runNodeStop(cmd *cobra.Command, args []string) error {
	pid, err := nodeconfig.ReadPID()
	if err != nil {
		msg := "No running node found."
		if nodeStopJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	proc, err := os.FindProcess(pid)
	if err != nil {
		nodeconfig.RemovePID()
		msg := fmt.Sprintf("Process %d not found.", pid)
		if nodeStopJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// Check if process is actually running
	if err := proc.Signal(syscall.Signal(0)); err != nil {
		nodeconfig.RemovePID()
		msg := "Node is not running (stale PID file removed)."
		if nodeStopJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Warning(msg)
		}
		return nil
	}

	// Send SIGTERM
	if err := proc.Signal(syscall.SIGTERM); err != nil {
		msg := fmt.Sprintf("Failed to stop node: %v", err)
		if nodeStopJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return err
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
			output.JSON(map[string]interface{}{"status": "success", "message": "Node stopped.", "pid": pid})
		} else {
			output.Success("Node stopped (PID %d).", pid)
		}
	} else {
		if nodeStopJSON {
			output.JSON(map[string]interface{}{"status": "warning", "message": "SIGTERM sent but process may still be running.", "pid": pid})
		} else {
			output.Warning("SIGTERM sent to PID %d but process may still be running.", pid)
		}
	}

	return nil
}
