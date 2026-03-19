package cmd

import (
	"fmt"
	"path/filepath"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow/handlers"
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

var nodeMarketplaceInstallJSON bool

var nodeMarketplaceInstallCmd = &cobra.Command{
	Use:   "install <slug>",
	Short: "Install a marketplace package",
	Long:  `Download and install a marketplace package to your node's endpoints directory.`,
	Args:  cobra.ExactArgs(1),
	RunE:  runNodeMarketplaceInstall,
}

func init() {
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

	if !nodeMarketplaceInstallJSON {
		fmt.Printf("Installing '%s' (%s)...\n", pkg.Name, pkg.Version)
	}

	if err := client.InstallPackage(cfg.EndpointsPath, slug, pkg.DownloadURL); err != nil {
		if nodeMarketplaceInstallJSON {
			output.JSON(map[string]any{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	// If the package has setup.yaml, run the setupflow engine for configuration.
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)
	spec, _ := nodeops.ParseSetupYaml(filepath.Join(endpointDir, "setup.yaml"))
	if spec != nil {
		if !nodeMarketplaceInstallJSON {
			fmt.Println()
			output.Info("Running setup...")
			fmt.Println()
		}

		state := &nodeops.SetupState{Version: "1", Steps: map[string]nodeops.StepState{}}
		engine := handlers.NewDefaultEngine()
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
