package cmd

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var (
	nodeInitHubURL        string
	nodeInitAPIKey        string
	nodeInitEndpointsPath string
	nodeInitPort          int
	nodeInitForce         bool
	nodeInitJSON          bool
)

var nodeInitCmd = &cobra.Command{
	Use:   "init",
	Short: "Initialize and start the node daemon",
	Long: `Initialize the SyftHub node configuration and start it as a background daemon.

Creates the shared configuration at ~/.config/syfthub/settings.json (the same
config used by syfthub-desktop). If no flags are provided and stdin is a
terminal, prompts interactively for required values.

The node always uses NATS tunneling mode (like syfthub-desktop). The tunnel
username is derived automatically from your API key at startup.

If a node is already running, use --force to reinitialize and restart it.`,
	RunE: runNodeInit,
}

func init() {
	nodeInitCmd.Flags().StringVar(&nodeInitHubURL, "hub-url", "", "SyftHub URL")
	nodeInitCmd.Flags().StringVar(&nodeInitAPIKey, "api-key", "", "API key or PAT")
	nodeInitCmd.Flags().StringVar(&nodeInitEndpointsPath, "endpoints-path", "", "Path to endpoints directory")
	nodeInitCmd.Flags().IntVar(&nodeInitPort, "port", 0, "HTTP server port")
	nodeInitCmd.Flags().BoolVar(&nodeInitForce, "force", false, "Overwrite existing configuration and restart")
	nodeInitCmd.Flags().BoolVar(&nodeInitJSON, "json", false, "Output result as JSON")
}

func runNodeInit(cmd *cobra.Command, args []string) error {
	// Check if already initialized
	existing := nodeconfig.Load()
	if existing.Configured() && !nodeInitForce {
		if nodeInitJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Node is already configured. Use --force to reinitialize.",
				"path":    nodeconfig.ConfigFile,
			})
		} else {
			output.Warning("Node is already configured at %s", nodeconfig.ConfigFile)
			output.Info("Use --force to reinitialize.")
		}
		return nil
	}

	// If forcing and a node is running, stop it first
	if nodeInitForce {
		stopExistingNode()
	}

	cfg := nodeconfig.DefaultNodeConfig()

	// Try to inherit hub URL and API key from main CLI config
	cliCfg := config.Load()
	if cliCfg.HubURL != "" {
		cfg.SyftHubURL = cliCfg.HubURL
	}
	if cliCfg.HasAPIToken() {
		cfg.APIKey = *cliCfg.APIToken
	}

	// Apply flag overrides
	if nodeInitHubURL != "" {
		cfg.SyftHubURL = nodeInitHubURL
	}
	if nodeInitAPIKey != "" {
		cfg.APIKey = nodeInitAPIKey
	}
	if nodeInitEndpointsPath != "" {
		cfg.EndpointsPath = nodeInitEndpointsPath
	}
	if nodeInitPort > 0 {
		cfg.Port = nodeInitPort
	}

	// Interactive prompting if TTY and missing required fields
	if term.IsTerminal(int(os.Stdin.Fd())) {
		reader := bufio.NewReader(os.Stdin)

		if cfg.SyftHubURL == "" || cmd.Flags().NFlag() == 0 {
			cfg.SyftHubURL = promptWithDefault(reader, "SyftHub URL", cfg.SyftHubURL)
		}
		if cfg.APIKey == "" {
			cfg.APIKey = promptRequired(reader, "API Key (PAT)")
		}
	}

	cfg.IsConfigured = true

	// Ensure config directory exists
	if err := nodeconfig.EnsureConfigDir(); err != nil {
		if nodeInitJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to create config directory: %v", err)
		}
		return err
	}

	// Create endpoints directory
	if err := os.MkdirAll(cfg.EndpointsPath, 0755); err != nil {
		if nodeInitJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to create endpoints directory: %v", err)
		}
		return err
	}

	if err := cfg.Save(); err != nil {
		if nodeInitJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save configuration: %v", err)
		}
		return err
	}

	// Start the daemon
	daemonPID, err := startNodeDaemon()
	if err != nil {
		if nodeInitJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": fmt.Sprintf("Config saved but failed to start daemon: %v", err),
			})
		} else {
			output.Error("Config saved but failed to start daemon: %v", err)
			fmt.Printf("  Config: %s\n", nodeconfig.ConfigFile)
			fmt.Println("  You can try starting manually with 'syft node run'")
		}
		return err
	}

	if nodeInitJSON {
		output.JSON(map[string]interface{}{
			"status":         "success",
			"config_path":    nodeconfig.ConfigFile,
			"endpoints_path": cfg.EndpointsPath,
			"syfthub_url":    cfg.SyftHubURL,
			"port":           cfg.Port,
			"pid":            daemonPID,
		})
	} else {
		output.Success("Node initialized and started!")
		fmt.Printf("  Config:    %s\n", nodeconfig.ConfigFile)
		fmt.Printf("  Endpoints: %s\n", cfg.EndpointsPath)
		fmt.Printf("  Hub URL:   %s\n", cfg.SyftHubURL)
		fmt.Printf("  Port:      %d\n", cfg.Port)
		fmt.Printf("  PID:       %d\n", daemonPID)
		fmt.Printf("  Logs:      %s\n", nodeconfig.LogFile)
		fmt.Println()
		fmt.Println("Use 'syft node logs -f' to follow daemon output.")
		fmt.Println("Use 'syft node stop' to stop the daemon.")
	}

	return nil
}

// startNodeDaemon spawns "syft node run" as a detached background process
// with stdout/stderr redirected to the log file.
func startNodeDaemon() (int, error) {
	// Find our own executable path
	exe, err := os.Executable()
	if err != nil {
		return 0, fmt.Errorf("failed to find executable path: %w", err)
	}

	// Open log file for daemon output
	logFile, err := os.OpenFile(nodeconfig.LogFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return 0, fmt.Errorf("failed to open log file: %w", err)
	}

	cmd := exec.Command(exe, "node", "run")
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Setsid: true, // Detach from parent session
	}

	if err := cmd.Start(); err != nil {
		logFile.Close()
		return 0, fmt.Errorf("failed to start daemon: %w", err)
	}

	pid := cmd.Process.Pid
	logFile.Close()

	// Release the process so it continues after we exit
	cmd.Process.Release()

	// Brief wait to check it didn't crash immediately
	time.Sleep(500 * time.Millisecond)
	proc, err := os.FindProcess(pid)
	if err == nil {
		if err := proc.Signal(syscall.Signal(0)); err != nil {
			return 0, fmt.Errorf("daemon exited immediately — check logs at %s", nodeconfig.LogFile)
		}
	}

	return pid, nil
}

// stopExistingNode stops any currently running node daemon.
func stopExistingNode() {
	pid, err := nodeconfig.ReadPID()
	if err != nil {
		return
	}
	proc, err := os.FindProcess(pid)
	if err != nil {
		nodeconfig.RemovePID()
		return
	}
	if err := proc.Signal(syscall.Signal(0)); err != nil {
		nodeconfig.RemovePID()
		return
	}
	_ = proc.Signal(syscall.SIGTERM)
	// Wait briefly for graceful shutdown
	for i := 0; i < 10; i++ {
		time.Sleep(500 * time.Millisecond)
		if err := proc.Signal(syscall.Signal(0)); err != nil {
			break
		}
	}
	nodeconfig.RemovePID()
}

func promptWithDefault(reader *bufio.Reader, label, defaultVal string) string {
	if defaultVal != "" {
		fmt.Printf("%s [%s]: ", label, defaultVal)
	} else {
		fmt.Printf("%s: ", label)
	}
	line, _ := reader.ReadString('\n')
	line = strings.TrimSpace(line)
	if line == "" {
		return defaultVal
	}
	return line
}

func promptRequired(reader *bufio.Reader, label string) string {
	for {
		fmt.Printf("%s: ", label)
		line, _ := reader.ReadString('\n')
		line = strings.TrimSpace(line)
		if line != "" {
			return line
		}
		fmt.Println("  This field is required.")
	}
}
