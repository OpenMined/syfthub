package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/connectors"
	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

var (
	setupInitConnectors []string
	setupInitList       bool
	setupInitForce      bool
	setupInitJSON       bool
)

var nodeEndpointSetupInitCmd = &cobra.Command{
	Use:   "setup-init <slug>",
	Short: "Generate setup.yaml from connector templates",
	Long: `Generate a setup.yaml file for an endpoint using built-in connector templates.

Use --connector to specify which platforms to include. Multiple connectors
can be combined into a single setup.yaml.

Examples:
  syft node endpoint setup-init my-bot --connector telegram
  syft node endpoint setup-init my-rag --connector google-drive --connector openai
  syft node endpoint setup-init --list  (show available connectors)`,
	Args: cobra.MaximumNArgs(1),
	RunE: runSetupInit,
}

func init() {
	nodeEndpointSetupInitCmd.Flags().StringSliceVar(&setupInitConnectors, "connector", nil, "Connector template IDs")
	nodeEndpointSetupInitCmd.Flags().BoolVar(&setupInitList, "list", false, "List available connector templates")
	nodeEndpointSetupInitCmd.Flags().BoolVar(&setupInitForce, "force", false, "Overwrite existing setup.yaml")
	nodeEndpointSetupInitCmd.Flags().BoolVar(&setupInitJSON, "json", false, "Output result as JSON")
}

func runSetupInit(cmd *cobra.Command, args []string) error {
	registry := connectors.NewRegistry()

	// List mode
	if setupInitList {
		templates := registry.List()

		if setupInitJSON {
			items := make([]map[string]any, len(templates))
			for i, m := range templates {
				items[i] = map[string]any{
					"id":          m.ID,
					"name":        m.Name,
					"category":    m.Category,
					"description": m.Description,
					"tags":        m.Tags,
				}
			}
			output.JSON(map[string]any{"status": output.StatusSuccess, "connectors": items})
			return nil
		}

		if len(templates) == 0 {
			fmt.Println("No connector templates available.")
			return nil
		}

		table := output.Table([]string{"ID", "NAME", "CATEGORY", "DESCRIPTION"})
		for _, m := range templates {
			desc := m.Description
			if len(desc) > 50 {
				desc = desc[:47] + "..."
			}
			table.Append([]string{m.ID, m.Name, m.Category, desc})
		}
		table.Render()
		return nil
	}

	// Scaffold mode requires a slug
	if len(args) == 0 {
		output.ReplyErrorSoft(setupInitJSON, "Endpoint slug is required. Usage: syft node endpoint setup-init <slug> --connector <id>")
		return nil
	}

	if len(setupInitConnectors) == 0 {
		output.ReplyErrorSoft(setupInitJSON, "At least one --connector is required. Use --list to see available connectors.")
		return nil
	}

	slug := args[0]
	cfg := nodeconfig.Load()
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)

	// Check endpoint exists
	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		output.ReplyErrorSoft(setupInitJSON, "Endpoint '%s' not found at %s.", slug, endpointDir)
		return nil
	}

	// Check setup.yaml doesn't already exist (unless --force)
	setupPath := filepath.Join(endpointDir, "setup.yaml")
	if _, err := os.Stat(setupPath); err == nil && !setupInitForce {
		output.ReplyErrorSoft(setupInitJSON, "setup.yaml already exists for '%s'. Use --force to overwrite.", slug)
		return nil
	}

	// Scaffold
	spec, err := registry.Scaffold(setupInitConnectors, nil)
	if err != nil {
		output.ReplyErrorSoft(setupInitJSON, "Failed to scaffold setup.yaml: %v", err)
		return nil
	}

	if err := nodeops.WriteSetupYaml(setupPath, spec); err != nil {
		output.ReplyErrorSoft(setupInitJSON, "Failed to write setup.yaml: %v", err)
		return nil
	}

	if setupInitJSON {
		output.JSON(map[string]any{
			"status":     output.StatusSuccess,
			"slug":       slug,
			"connectors": setupInitConnectors,
			"path":       setupPath,
		})
	} else {
		output.Success("Generated setup.yaml with connectors: %s", strings.Join(setupInitConnectors, ", "))
		output.Info("Review and customize: %s", setupPath)
		output.Info("Then run: syft node endpoint setup %s", slug)
	}
	return nil
}
