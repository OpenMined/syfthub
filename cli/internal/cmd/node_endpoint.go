package cmd

import (
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/OpenMined/syfthub/pkg/nodeops"
)

// --- Parent command ---

var nodeEndpointCmd = &cobra.Command{
	Use:     "endpoint",
	Aliases: []string{"ep"},
	Short:   "Manage local endpoints",
	Long:    `Create, list, edit, and delete endpoints in your local node.`,
}

func init() {
	nodeEndpointCmd.AddCommand(nodeEndpointCreateCmd)
	nodeEndpointCmd.AddCommand(nodeEndpointListCmd)
	nodeEndpointCmd.AddCommand(nodeEndpointDeleteCmd)
	nodeEndpointCmd.AddCommand(nodeEndpointEditCmd)
}

// --- Create ---

var (
	nodeEPCreateType        string
	nodeEPCreateDescription string
	nodeEPCreateVersion     string
	nodeEPCreateJSON        bool
)

var nodeEndpointCreateCmd = &cobra.Command{
	Use:   "create <name>",
	Short: "Create a new endpoint",
	Long:  `Scaffold a new endpoint directory with runner.py, pyproject.toml, and README.md.`,
	Args:  cobra.ExactArgs(1),
	RunE:  runNodeEndpointCreate,
}

func init() {
	nodeEndpointCreateCmd.Flags().StringVar(&nodeEPCreateType, "type", "", "Endpoint type: model or data_source (required)")
	nodeEndpointCreateCmd.Flags().StringVar(&nodeEPCreateDescription, "description", "", "Endpoint description")
	nodeEndpointCreateCmd.Flags().StringVar(&nodeEPCreateVersion, "version", "", "Endpoint version (default: 1.0.0)")
	nodeEndpointCreateCmd.Flags().BoolVar(&nodeEPCreateJSON, "json", false, "Output result as JSON")
	nodeEndpointCreateCmd.MarkFlagRequired("type")
}

func runNodeEndpointCreate(cmd *cobra.Command, args []string) error {
	cfg := nodeconfig.Load()
	mgr := nodeops.NewManager(cfg.EndpointsPath)

	slug, err := mgr.CreateEndpoint(nodeops.CreateEndpointRequest{
		Name:        args[0],
		Type:        nodeEPCreateType,
		Description: nodeEPCreateDescription,
		Version:     nodeEPCreateVersion,
	})
	if err != nil {
		if nodeEPCreateJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	if nodeEPCreateJSON {
		output.JSON(map[string]interface{}{
			"status": "success",
			"slug":   slug,
			"path":   fmt.Sprintf("%s/%s", cfg.EndpointsPath, slug),
		})
	} else {
		output.Success("Created endpoint '%s' (%s)", slug, nodeEPCreateType)
		fmt.Printf("  Path: %s/%s\n", cfg.EndpointsPath, slug)
	}
	return nil
}

// --- List ---

var (
	nodeEPListLong bool
	nodeEPListJSON bool
)

var nodeEndpointListCmd = &cobra.Command{
	Use:   "list",
	Short: "List local endpoints",
	Long:  `List all endpoints in the local node's endpoints directory.`,
	RunE:  runNodeEndpointList,
}

func init() {
	nodeEndpointListCmd.Flags().BoolVarP(&nodeEPListLong, "long", "l", false, "Show detailed table")
	nodeEndpointListCmd.Flags().BoolVar(&nodeEPListJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointList(cmd *cobra.Command, args []string) error {
	cfg := nodeconfig.Load()
	mgr := nodeops.NewManager(cfg.EndpointsPath)

	endpoints, err := mgr.ListEndpoints()
	if err != nil {
		if nodeEPListJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	if len(endpoints) == 0 {
		if nodeEPListJSON {
			output.JSON(map[string]interface{}{"status": "success", "endpoints": []interface{}{}})
		} else {
			fmt.Println("No endpoints found.")
			fmt.Printf("Create one with: syft node endpoint create <name> --type model\n")
		}
		return nil
	}

	if nodeEPListJSON {
		output.JSON(map[string]interface{}{"status": "success", "endpoints": endpoints})
		return nil
	}

	if nodeEPListLong {
		table := output.Table([]string{"SLUG", "NAME", "TYPE", "VERSION", "ENABLED", "POLICIES", "DEPS"})
		for _, ep := range endpoints {
			enabled := output.Green.Sprint("yes")
			if !ep.Enabled {
				enabled = output.Red.Sprint("no")
			}
			policies := "-"
			if ep.HasPolicies {
				policies = output.Yellow.Sprint("yes")
			}
			table.Append([]string{
				ep.Slug,
				ep.Name,
				ep.Type,
				ep.Version,
				enabled,
				policies,
				fmt.Sprintf("%d", ep.DepsCount),
			})
		}
		table.Render()
	} else {
		for _, ep := range endpoints {
			icon := output.TypeIcon(ep.Type)
			enabled := ""
			if !ep.Enabled {
				enabled = output.Dim.Sprint(" (disabled)")
			}
			fmt.Printf("  %s %s%s\n", icon, ep.Slug, enabled)
		}
	}

	return nil
}

// --- Delete ---

var (
	nodeEPDeleteForce bool
	nodeEPDeleteJSON  bool
)

var nodeEndpointDeleteCmd = &cobra.Command{
	Use:   "delete <slug>",
	Short: "Delete an endpoint",
	Long:  `Delete a local endpoint directory and all its contents.`,
	Args:  cobra.ExactArgs(1),
	RunE:  runNodeEndpointDelete,
}

func init() {
	nodeEndpointDeleteCmd.Flags().BoolVar(&nodeEPDeleteForce, "force", false, "Skip confirmation prompt")
	nodeEndpointDeleteCmd.Flags().BoolVar(&nodeEPDeleteJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointDelete(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()
	mgr := nodeops.NewManager(cfg.EndpointsPath)

	// Confirmation prompt
	if !nodeEPDeleteForce && term.IsTerminal(int(os.Stdin.Fd())) {
		fmt.Printf("Delete endpoint '%s'? This cannot be undone. [y/N]: ", slug)
		var confirm string
		fmt.Scanln(&confirm)
		if strings.ToLower(confirm) != "y" {
			fmt.Println("Cancelled.")
			return nil
		}
	}

	if err := mgr.DeleteEndpoint(slug); err != nil {
		if nodeEPDeleteJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	if nodeEPDeleteJSON {
		output.JSON(map[string]interface{}{"status": "success", "slug": slug})
	} else {
		output.Success("Deleted endpoint '%s'.", slug)
	}
	return nil
}

// --- Edit ---

var (
	nodeEPEditName        string
	nodeEPEditDescription string
	nodeEPEditType        string
	nodeEPEditVersion     string
	nodeEPEditEnabled     string
	nodeEPEditJSON        bool
)

var nodeEndpointEditCmd = &cobra.Command{
	Use:   "edit <slug>",
	Short: "Edit endpoint metadata",
	Long:  `Modify endpoint name, description, type, version, or enabled status via flags.`,
	Args:  cobra.ExactArgs(1),
	RunE:  runNodeEndpointEdit,
}

func init() {
	nodeEndpointEditCmd.Flags().StringVar(&nodeEPEditName, "name", "", "Set endpoint name")
	nodeEndpointEditCmd.Flags().StringVar(&nodeEPEditDescription, "description", "", "Set endpoint description")
	nodeEndpointEditCmd.Flags().StringVar(&nodeEPEditType, "type", "", "Set endpoint type (model or data_source)")
	nodeEndpointEditCmd.Flags().StringVar(&nodeEPEditVersion, "version", "", "Set endpoint version")
	nodeEndpointEditCmd.Flags().StringVar(&nodeEPEditEnabled, "enabled", "", "Set enabled status (true or false)")
	nodeEndpointEditCmd.Flags().BoolVar(&nodeEPEditJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointEdit(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()

	readmePath := fmt.Sprintf("%s/%s/README.md", cfg.EndpointsPath, slug)

	// Build updates from flags
	updates := make(map[string]interface{})
	if cmd.Flags().Changed("name") {
		updates["name"] = nodeEPEditName
	}
	if cmd.Flags().Changed("description") {
		updates["description"] = nodeEPEditDescription
	}
	if cmd.Flags().Changed("type") {
		if nodeEPEditType != "model" && nodeEPEditType != "data_source" {
			msg := "type must be 'model' or 'data_source'"
			if nodeEPEditJSON {
				output.JSON(map[string]interface{}{"status": "error", "message": msg})
			} else {
				output.Error(msg)
			}
			return nil
		}
		updates["type"] = nodeEPEditType
	}
	if cmd.Flags().Changed("version") {
		updates["version"] = nodeEPEditVersion
	}
	if cmd.Flags().Changed("enabled") {
		switch strings.ToLower(nodeEPEditEnabled) {
		case "true", "yes", "1":
			updates["enabled"] = true
		case "false", "no", "0":
			updates["enabled"] = false
		default:
			msg := "enabled must be 'true' or 'false'"
			if nodeEPEditJSON {
				output.JSON(map[string]interface{}{"status": "error", "message": msg})
			} else {
				output.Error(msg)
			}
			return nil
		}
	}

	if len(updates) == 0 {
		msg := "No changes specified. Use --name, --description, --type, --version, or --enabled flags."
		if nodeEPEditJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	if err := nodeops.UpdateReadmeFrontmatter(readmePath, updates); err != nil {
		if nodeEPEditJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
		} else {
			output.Error("%v", err)
		}
		return nil
	}

	if nodeEPEditJSON {
		updates["status"] = "success"
		updates["slug"] = slug
		output.JSON(updates)
	} else {
		output.Success("Updated endpoint '%s'.", slug)
		for k, v := range updates {
			fmt.Printf("  %s: %v\n", k, v)
		}
	}
	return nil
}
