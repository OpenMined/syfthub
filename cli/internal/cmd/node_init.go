package cmd

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var (
	nodeInitHubURL        string
	nodeInitAPIKey        string
	nodeInitSpaceURL      string
	nodeInitEndpointsPath string
	nodeInitPort          int
	nodeInitForce         bool
	nodeInitJSON          bool
)

var nodeInitCmd = &cobra.Command{
	Use:   "init",
	Short: "Initialize node configuration",
	Long: `Initialize the SyftHub node configuration at ~/.syfthub/node/.

Creates the configuration directory and config file. If no flags are provided
and stdin is a terminal, prompts interactively for required values.`,
	RunE: runNodeInit,
}

func init() {
	nodeInitCmd.Flags().StringVar(&nodeInitHubURL, "hub-url", "", "SyftHub URL")
	nodeInitCmd.Flags().StringVar(&nodeInitAPIKey, "api-key", "", "API key or PAT")
	nodeInitCmd.Flags().StringVar(&nodeInitSpaceURL, "space-url", "", "Space URL or tunneling:username")
	nodeInitCmd.Flags().StringVar(&nodeInitEndpointsPath, "endpoints-path", "", "Path to endpoints directory")
	nodeInitCmd.Flags().IntVar(&nodeInitPort, "port", 0, "HTTP server port")
	nodeInitCmd.Flags().BoolVar(&nodeInitForce, "force", false, "Overwrite existing configuration")
	nodeInitCmd.Flags().BoolVar(&nodeInitJSON, "json", false, "Output result as JSON")
}

func runNodeInit(cmd *cobra.Command, args []string) error {
	// Check if already initialized
	existing := nodeconfig.Load()
	if existing.IsConfigured() && !nodeInitForce {
		if nodeInitJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Node is already configured. Use --force to reinitialize.",
				"path":    nodeconfig.NodeConfigFile,
			})
		} else {
			output.Warning("Node is already configured at %s", nodeconfig.NodeConfigFile)
			output.Info("Use --force to reinitialize.")
		}
		return nil
	}

	cfg := nodeconfig.DefaultNodeConfig()

	// Try to inherit hub URL and API key from main CLI config
	cliCfg := config.Load()
	if cliCfg.HubURL != "" {
		cfg.SyftHubURL = cliCfg.HubURL
	}
	if cliCfg.HasTokens() {
		cfg.APIKey = *cliCfg.AccessToken
	}

	// Apply flag overrides
	if nodeInitHubURL != "" {
		cfg.SyftHubURL = nodeInitHubURL
	}
	if nodeInitAPIKey != "" {
		cfg.APIKey = nodeInitAPIKey
	}
	if nodeInitSpaceURL != "" {
		cfg.SpaceURL = nodeInitSpaceURL
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
		if cfg.SpaceURL == "" {
			cfg.SpaceURL = promptWithDefault(reader, "Space URL (or tunneling:username)", "")
		}
	}

	// Ensure directories exist
	if err := nodeconfig.EnsureNodeDir(); err != nil {
		if nodeInitJSON {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to create node directory: %v", err)
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

	if nodeInitJSON {
		output.JSON(map[string]interface{}{
			"status":         "success",
			"config_path":    nodeconfig.NodeConfigFile,
			"endpoints_path": cfg.EndpointsPath,
			"syfthub_url":    cfg.SyftHubURL,
			"port":           cfg.Port,
		})
	} else {
		output.Success("Node initialized successfully!")
		fmt.Printf("  Config:    %s\n", nodeconfig.NodeConfigFile)
		fmt.Printf("  Endpoints: %s\n", cfg.EndpointsPath)
		fmt.Printf("  Hub URL:   %s\n", cfg.SyftHubURL)
		fmt.Printf("  Port:      %d\n", cfg.Port)
	}

	return nil
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
