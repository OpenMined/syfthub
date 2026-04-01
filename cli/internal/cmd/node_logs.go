package cmd

import (
	"fmt"
	"io"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var nodeLogsFollow bool

var nodeLogsCmd = &cobra.Command{
	Use:         "logs",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "View node daemon logs",
	Long:        `Display the SyftHub node daemon log output. Use -f to follow (tail) in real time.`,
	RunE:        runNodeLogs,
}

func init() {
	nodeLogsCmd.Flags().BoolVarP(&nodeLogsFollow, "follow", "f", false, "Follow log output (like tail -f)")
}

func runNodeLogs(cmd *cobra.Command, args []string) error {
	logFile := nodeconfig.LogFile

	f, err := os.Open(logFile)
	if err != nil {
		if os.IsNotExist(err) {
			output.Error("No log file found at %s", logFile)
			fmt.Println("Has the node been started? Run 'syft node init' first.")
			return nil
		}
		return fmt.Errorf("failed to open log file: %w", err)
	}
	defer f.Close()

	if !nodeLogsFollow {
		// Print the entire log file
		if _, err := io.Copy(os.Stdout, f); err != nil {
			return fmt.Errorf("failed to read log file: %w", err)
		}
		return nil
	}

	// Seek to end, then follow
	if _, err := f.Seek(0, io.SeekEnd); err != nil {
		return fmt.Errorf("failed to seek log file: %w", err)
	}

	buf := make([]byte, 4096)
	for {
		n, err := f.Read(buf)
		if n > 0 {
			os.Stdout.Write(buf[:n])
		}
		if err == io.EOF {
			time.Sleep(200 * time.Millisecond)
			continue
		}
		if err != nil {
			return fmt.Errorf("error reading log file: %w", err)
		}
	}
}
