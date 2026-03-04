package cmd

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/OpenMined/syfthub/pkg/nodeops"
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
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	client := nodeops.NewMarketplaceClient(manifestURL)
	packages, err := client.FetchPackages()
	if err != nil {
		if nodeMarketplaceListJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	if nodeMarketplaceListJSON {
		output.JSON(map[string]interface{}{"status": "success", "packages": packages})
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
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
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
			output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
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
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// Parse config values
	var configValues []nodeops.EnvVar
	for _, kv := range nodeMarketplaceInstallConfig {
		parts := strings.SplitN(kv, "=", 2)
		if len(parts) != 2 {
			msg := fmt.Sprintf("Invalid config format: %q (expected key=value)", kv)
			if nodeMarketplaceInstallJSON {
				output.JSON(map[string]interface{}{"status": "error", "message": msg})
			} else {
				output.Error(msg)
			}
			return nil
		}
		configValues = append(configValues, nodeops.EnvVar{Key: parts[0], Value: parts[1]})
	}

	if !nodeMarketplaceInstallJSON {
		fmt.Printf("Installing '%s' (%s)...\n", pkg.Name, pkg.Version)
	}

	if err := client.InstallPackage(cfg.EndpointsPath, slug, pkg.DownloadURL, configValues); err != nil {
		if nodeMarketplaceInstallJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	if nodeMarketplaceInstallJSON {
		output.JSON(map[string]interface{}{
			"status": "success",
			"slug":   slug,
			"path":   fmt.Sprintf("%s/%s", cfg.EndpointsPath, slug),
		})
	} else {
		output.Success("Installed '%s' to %s/%s", pkg.Name, cfg.EndpointsPath, slug)
	}
	return nil
}
