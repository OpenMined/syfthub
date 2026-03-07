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
			items := make([]map[string]interface{}, len(templates))
			for i, m := range templates {
				items[i] = map[string]interface{}{
					"id":          m.ID,
					"name":        m.Name,
					"category":    m.Category,
					"description": m.Description,
					"tags":        m.Tags,
				}
			}
			output.JSON(map[string]interface{}{"status": "success", "connectors": items})
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
		msg := "Endpoint slug is required. Usage: syft node endpoint setup-init <slug> --connector <id>"
		if setupInitJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	if len(setupInitConnectors) == 0 {
		msg := "At least one --connector is required. Use --list to see available connectors."
		if setupInitJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	slug := args[0]
	cfg := nodeconfig.Load()
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)

	// Check endpoint exists
	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		msg := fmt.Sprintf("Endpoint '%s' not found at %s.", slug, endpointDir)
		if setupInitJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// Check setup.yaml doesn't already exist (unless --force)
	setupPath := filepath.Join(endpointDir, "setup.yaml")
	if _, err := os.Stat(setupPath); err == nil && !setupInitForce {
		msg := fmt.Sprintf("setup.yaml already exists for '%s'. Use --force to overwrite.", slug)
		if setupInitJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// Scaffold
	spec, err := registry.Scaffold(setupInitConnectors, nil)
	if err != nil {
		msg := fmt.Sprintf("Failed to scaffold setup.yaml: %v", err)
		if setupInitJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	if err := nodeops.WriteSetupYaml(setupPath, spec); err != nil {
		msg := fmt.Sprintf("Failed to write setup.yaml: %v", err)
		if setupInitJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	if setupInitJSON {
		output.JSON(map[string]interface{}{
			"status":     "success",
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
