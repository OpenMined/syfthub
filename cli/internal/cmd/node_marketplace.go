package cmd

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// --- Parent command ---

var nodeMarketplaceCmd = &cobra.Command{
	Use:     "marketplace",
	Aliases: []string{"mp"},
	Short:   "Browse and install marketplace packages",
	Long:    `List available marketplace packages and install them to your node.`,
}

func init() {
	nodeMarketplaceCmd.AddCommand(nodeMarketplaceListCmd)
	nodeMarketplaceCmd.AddCommand(nodeMarketplaceInstallCmd)
}

// --- List ---

var nodeMarketplaceListJSON bool

var nodeMarketplaceListCmd = &cobra.Command{
	Use:   "list",
	Short: "List available marketplace packages",
	Long:  `Fetch and display available packages from the SyftHub marketplace.`,
	RunE:  runNodeMarketplaceList,
}

func init() {
	nodeMarketplaceListCmd.Flags().BoolVar(&nodeMarketplaceListJSON, "json", false, "Output result as JSON")
}

func runNodeMarketplaceList(cmd *cobra.Command, args []string) error {
	cfg := nodeconfig.Load()
	manifestURL := cfg.GetMarketplaceURL()
	if manifestURL == "" {
		msg := "Marketplace URL not configured."
		if nodeMarketplaceListJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	client := nodeops.NewMarketplaceClient(manifestURL)
	packages, err := client.FetchPackages()
	if err != nil {
		if nodeMarketplaceListJSON {
			output.JSON(map[string]any{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	if nodeMarketplaceListJSON {
		output.JSON(map[string]any{"status": "success", "packages": packages})
		return nil
	}

	if len(packages) == 0 {
		fmt.Println("No marketplace packages available.")
		return nil
	}

	table := output.Table([]string{"SLUG", "NAME", "TYPE", "VERSION", "DESCRIPTION"})
	for _, pkg := range packages {
		desc := pkg.Description
		if len(desc) > 60 {
			desc = desc[:57] + "..."
		}
		table.Append([]string{
			pkg.Slug,
			pkg.Name,
			pkg.Type,
			pkg.Version,
			desc,
		})
	}
	table.Render()

	return nil
}

// --- Install ---

var (
	nodeMarketplaceInstallConfig []string
	nodeMarketplaceInstallJSON   bool
)

var nodeMarketplaceInstallCmd = &cobra.Command{
	Use:   "install <slug>",
	Short: "Install a marketplace package",
	Long: `Download and install a marketplace package to your node's endpoints directory.

Use --config to provide required configuration values (e.g., API keys).`,
	Args: cobra.ExactArgs(1),
	RunE: runNodeMarketplaceInstall,
}

func init() {
	nodeMarketplaceInstallCmd.Flags().StringSliceVar(&nodeMarketplaceInstallConfig, "config", nil, "Config key=value pairs (repeatable)")
	nodeMarketplaceInstallCmd.Flags().BoolVar(&nodeMarketplaceInstallJSON, "json", false, "Output result as JSON")
}

func runNodeMarketplaceInstall(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()

	manifestURL := cfg.GetMarketplaceURL()
	if manifestURL == "" {
		msg := "Marketplace URL not configured."
		if nodeMarketplaceInstallJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	client := nodeops.NewMarketplaceClient(manifestURL)

	// Fetch manifest to find the package
	packages, err := client.FetchPackages()
	if err != nil {
		if nodeMarketplaceInstallJSON {
			output.JSON(map[string]any{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	// Find the package
	var pkg *nodeops.MarketplacePackage
	for i := range packages {
		if packages[i].Slug == slug {
			pkg = &packages[i]
			break
		}
	}

	if pkg == nil {
		msg := fmt.Sprintf("Package '%s' not found in marketplace.", slug)
		if nodeMarketplaceInstallJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// Build config values from --config flags
	flagConfig := make(map[string]string)
	for _, kv := range nodeMarketplaceInstallConfig {
		parts := strings.SplitN(kv, "=", 2)
		if len(parts) != 2 {
			msg := fmt.Sprintf("Invalid config format: %q (expected key=value)", kv)
			if nodeMarketplaceInstallJSON {
				output.JSON(map[string]any{"status": "error", "message": msg})
			} else {
				output.Error(msg)
			}
			return nil
		}
		flagConfig[parts[0]] = parts[1]
	}

	if !nodeMarketplaceInstallJSON {
		fmt.Printf("Installing '%s' (%s)...\n", pkg.Name, pkg.Version)
	}

	// Install first (extract ZIP), then configure.
	// Pass only --config flag values so the ZIP is extracted without interactive prompts.
	var flagValues []nodeops.EnvVar
	for k, v := range flagConfig {
		flagValues = append(flagValues, nodeops.EnvVar{Key: k, Value: v})
	}

	if err := client.InstallPackage(cfg.EndpointsPath, slug, pkg.DownloadURL, flagValues); err != nil {
		if nodeMarketplaceInstallJSON {
			output.JSON(map[string]any{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	// If the package has setup.yaml, use the setupflow engine for configuration.
	// Otherwise, fall back to legacy interactive config prompts from manifest.
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)
	spec, _ := nodeops.ParseSetupYaml(filepath.Join(endpointDir, "setup.yaml"))
	if spec != nil {
		if !nodeMarketplaceInstallJSON {
			fmt.Println()
			output.Info("Running setup...")
			fmt.Println()
		}

		state := &nodeops.SetupState{Version: "1", Steps: map[string]nodeops.StepState{}}
		engine := newSetupEngine()
		sio := NewCLISetupIO()
		sctx := &setupflow.SetupContext{
			EndpointDir: endpointDir,
			Slug:        slug,
			HubURL:      cfg.SyftHubURL,
			APIKey:      cfg.APIKey,
			IO:          sio,
			StepOutputs: make(map[string]*setupflow.StepResult),
			State:       state,
			Spec:        spec,
		}
		if err := engine.Execute(sctx); err != nil {
			output.Warning("Setup incomplete: %v", err)
			output.Info("Run 'syft node endpoint setup %s' to complete configuration.", slug)
		}
	} else if len(pkg.Config) > 0 {
		// Legacy config prompts for packages without setup.yaml
		if !nodeMarketplaceInstallJSON {
			fmt.Printf("\n  '%s' requires configuration:\n\n", pkg.Name)
		}

		var configValues []nodeops.EnvVar
		reader := bufio.NewReader(os.Stdin)
		for _, field := range pkg.Config {
			// Check if value was provided via --config flag
			if val, ok := flagConfig[field.Key]; ok {
				configValues = append(configValues, nodeops.EnvVar{Key: field.Key, Value: val})
				continue
			}

			// In JSON mode, don't prompt — just use defaults
			if nodeMarketplaceInstallJSON {
				if field.Default != "" {
					configValues = append(configValues, nodeops.EnvVar{Key: field.Key, Value: field.Default})
				}
				continue
			}

			label := field.Label
			if label == "" {
				label = field.Key
			}
			if field.Description != "" {
				output.Dim.Printf("  %s\n", field.Description)
			}

			reqTag := ""
			if field.Required {
				reqTag = " (required)"
			}

			var value string
			if field.Secret {
				for {
					if field.Default != "" {
						fmt.Printf("  %s%s [****]: ", label, reqTag)
					} else {
						fmt.Printf("  %s%s: ", label, reqTag)
					}
					byteVal, err := term.ReadPassword(int(syscall.Stdin))
					fmt.Println()
					if err != nil {
						return fmt.Errorf("failed to read input: %w", err)
					}
					value = strings.TrimSpace(string(byteVal))
					if value == "" {
						value = field.Default
					}
					if value != "" || !field.Required {
						break
					}
					fmt.Println("    This field is required.")
				}
			} else {
				for {
					if field.Default != "" {
						fmt.Printf("  %s%s [%s]: ", label, reqTag, field.Default)
					} else {
						fmt.Printf("  %s%s: ", label, reqTag)
					}
					line, _ := reader.ReadString('\n')
					value = strings.TrimSpace(line)
					if value == "" {
						value = field.Default
					}
					if value != "" || !field.Required {
						break
					}
					fmt.Println("    This field is required.")
				}
			}

			if value != "" {
				configValues = append(configValues, nodeops.EnvVar{Key: field.Key, Value: value})
			}
		}

		if !nodeMarketplaceInstallJSON {
			fmt.Println()
		}

		// Write legacy config values to .env
		if len(configValues) > 0 {
			envPath := filepath.Join(endpointDir, ".env")
			if err := nodeops.WriteEnvFile(envPath, configValues); err != nil {
				output.Warning("Failed to write config: %v", err)
			}
		}
	}

	if nodeMarketplaceInstallJSON {
		output.JSON(map[string]any{
			"status": "success",
			"slug":   slug,
			"path":   fmt.Sprintf("%s/%s", cfg.EndpointsPath, slug),
		})
	} else {
		output.Success("Installed '%s' to %s/%s", pkg.Name, cfg.EndpointsPath, slug)
	}
	return nil
}
