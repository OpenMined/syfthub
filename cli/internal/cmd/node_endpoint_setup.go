package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow/handlers"
)

var (
	nodeEPSetupForce bool
	nodeEPSetupStep  []string
	nodeEPSetupJSON  bool
)

var nodeEndpointSetupCmd = &cobra.Command{
	Use:   "setup <slug>",
	Short: "Run or resume endpoint configuration",
	Long: `Execute the setup steps defined in an endpoint's setup.yaml.

If setup was previously interrupted, it resumes from the last incomplete step.
Use --force to re-run all steps. Use --step to run specific steps only.`,
	Args: cobra.ExactArgs(1),
	RunE: runNodeEndpointSetup,
}

func init() {
	nodeEndpointSetupCmd.Flags().BoolVar(&nodeEPSetupForce, "force", false, "Re-run all steps")
	nodeEndpointSetupCmd.Flags().StringSliceVar(&nodeEPSetupStep, "step", nil, "Run specific step IDs only")
	nodeEndpointSetupCmd.Flags().BoolVar(&nodeEPSetupJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointSetup(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)

	// 1. Verify endpoint exists
	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		msg := fmt.Sprintf("Endpoint '%s' not found.", slug)
		if nodeEPSetupJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// 2. Parse setup.yaml
	setupPath := filepath.Join(endpointDir, "setup.yaml")
	spec, err := nodeops.ParseSetupYaml(setupPath)
	if err != nil {
		msg := fmt.Sprintf("Failed to parse setup.yaml: %v", err)
		if nodeEPSetupJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}
	if spec == nil {
		msg := fmt.Sprintf("No setup.yaml found for endpoint '%s'.", slug)
		if nodeEPSetupJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// 3. Load existing state
	state, _ := nodeops.ReadSetupState(endpointDir)
	if state == nil {
		state = &nodeops.SetupState{Version: "1", Steps: map[string]nodeops.StepState{}}
	}

	// 4. Create engine and context
	engine := handlers.NewDefaultEngine()
	sio := NewCLISetupIO()

	ctx := &setupflow.SetupContext{
		EndpointDir: endpointDir,
		Slug:        slug,
		HubURL:      cfg.HubURL,
		APIKey:      cfg.APIToken,
		IO:          sio,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       state,
		Spec:        spec,
		Force:       nodeEPSetupForce,
		OnlySteps:   nodeEPSetupStep,
	}

	// 5. Execute
	if !nodeEPSetupJSON {
		fmt.Printf("\nSetting up endpoint '%s'...\n\n", slug)
	}

	if err := engine.Execute(ctx); err != nil {
		msg := fmt.Sprintf("Setup failed: %v", err)
		if nodeEPSetupJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	// 6. Report result
	status, _ := nodeops.GetSetupStatus(endpointDir)
	if nodeEPSetupJSON {
		output.JSON(map[string]any{"status": "success", "setup_status": status})
	} else {
		if status != nil {
			output.Success("Setup complete for '%s' (%d/%d steps)", slug, status.CompletedN, status.TotalSteps)
		} else {
			output.Success("Setup complete for '%s'", slug)
		}
	}
	return nil
}

// --- Setup Status ---

var nodeEPSetupStatusJSON bool

var nodeEndpointSetupStatusCmd = &cobra.Command{
	Use:   "setup-status <slug>",
	Short: "Show setup status for an endpoint",
	Args:  cobra.ExactArgs(1),
	RunE:  runNodeEndpointSetupStatus,
}

func init() {
	nodeEndpointSetupStatusCmd.Flags().BoolVar(&nodeEPSetupStatusJSON, "json", false, "Output result as JSON")
}

func runNodeEndpointSetupStatus(cmd *cobra.Command, args []string) error {
	slug := args[0]
	cfg := nodeconfig.Load()
	endpointDir := filepath.Join(cfg.EndpointsPath, slug)

	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		msg := fmt.Sprintf("Endpoint '%s' not found.", slug)
		if nodeEPSetupStatusJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	status, err := nodeops.GetSetupStatus(endpointDir)
	if err != nil {
		output.Error("Failed to get setup status: %v", err)
		return nil
	}

	if status == nil {
		msg := fmt.Sprintf("Endpoint '%s' has no setup.yaml.", slug)
		if nodeEPSetupStatusJSON {
			output.JSON(map[string]any{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return nil
	}

	if nodeEPSetupStatusJSON {
		output.JSON(map[string]any{"status": "success", "setup_status": status})
		return nil
	}

	// Load spec for detailed view
	spec, _ := nodeops.ParseSetupYaml(filepath.Join(endpointDir, "setup.yaml"))
	state, _ := nodeops.ReadSetupState(endpointDir)

	fmt.Printf("\nSetup status for '%s':\n\n", slug)

	table := output.Table([]string{"STEP", "TYPE", "REQUIRED", "STATUS"})
	for _, step := range spec.Steps {
		stepStatus := nodeops.StepStatusPending
		if state != nil {
			if ss, ok := state.Steps[step.ID]; ok {
				stepStatus = ss.Status
				if ss.ExpiresAt != "" {
					stepStatus += " (expires: " + ss.ExpiresAt + ")"
				}
			}
		}
		required := "no"
		if step.Required {
			required = "yes"
		}
		table.Append([]string{step.Name, step.Type, required, stepStatus})
	}
	table.Render()

	fmt.Println()
	if status.IsComplete {
		output.Success("All steps complete (%d/%d)", status.CompletedN, status.TotalSteps)
	} else {
		if len(status.PendingSteps) > 0 {
			output.Warning("Pending steps: %s", strings.Join(status.PendingSteps, ", "))
		}
		if len(status.ExpiredSteps) > 0 {
			output.Warning("Expired steps: %s", strings.Join(status.ExpiredSteps, ", "))
		}
		output.Info("Run 'syft node endpoint setup %s' to complete configuration.", slug)
	}

	return nil
}
