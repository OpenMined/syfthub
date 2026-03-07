package cmd

import (
	"fmt"
	"net/http"
	"os"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

var nodeStatusJSON bool

var nodeStatusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show node status",
	Long:  `Show whether the SyftHub node is running and display configuration summary.`,
	RunE:  runNodeStatus,
}

func init() {
	nodeStatusCmd.Flags().BoolVar(&nodeStatusJSON, "json", false, "Output result as JSON")
}

func runNodeStatus(cmd *cobra.Command, args []string) error {
	cfg := nodeconfig.Load()

	running := false
	pid := 0
	if p, err := nodeconfig.ReadPID(); err == nil {
		pid = p
		proc, err := os.FindProcess(p)
		if err == nil {
			if err := proc.Signal(syscall.Signal(0)); err == nil {
				running = true
			}
		}
		if !running {
			// Stale PID file
			nodeconfig.RemovePID()
			pid = 0
		}
	}

	// Check if HTTP server is responding
	serverReachable := false
	if running {
		healthURL := fmt.Sprintf("http://localhost:%d/health", cfg.Port)
		client := &http.Client{Timeout: 2 * time.Second}
		if resp, err := client.Get(healthURL); err == nil {
			resp.Body.Close()
			serverReachable = resp.StatusCode == http.StatusOK
		}
	}

	// Count endpoints
	endpointCount := 0
	if cfg.EndpointsPath != "" {
		mgr := nodeops.NewManager(cfg.EndpointsPath)
		if eps, err := mgr.ListEndpoints(); err == nil {
			endpointCount = len(eps)
		}
	}

	if nodeStatusJSON {
		data := map[string]interface{}{
			"status":           "success",
			"running":          running,
			"server_reachable": serverReachable,
			"configured":       cfg.Configured(),
			"pid":              pid,
			"syfthub_url":      cfg.SyftHubURL,
			"endpoints_path":   cfg.EndpointsPath,
			"endpoint_count":   endpointCount,
			"port":             cfg.Port,
		}
		output.JSON(data)
		return nil
	}

	if running {
		output.Success("Node is running (PID %d)", pid)
		if serverReachable {
			fmt.Printf("  Server:    listening on port %d\n", cfg.Port)
		} else {
			fmt.Printf("  Server:    not yet reachable on port %d\n", cfg.Port)
		}
	} else {
		fmt.Println("Node is not running.")
	}

	fmt.Println()
	if cfg.Configured() {
		fmt.Printf("  Hub URL:   %s\n", cfg.SyftHubURL)
		fmt.Printf("  Endpoints: %d in %s\n", endpointCount, cfg.EndpointsPath)
		fmt.Printf("  Port:      %d\n", cfg.Port)
	} else {
		fmt.Println("  Not configured. Run 'syft node init' to set up.")
	}

	return nil
}
