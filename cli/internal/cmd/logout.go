package cmd

import (
	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var logoutJSONOutput bool

var logoutCmd = &cobra.Command{
	Use:         "logout",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "Clear stored API token",
	Long: `Clear the stored API token from the local configuration.

Note: This does not revoke the token on the server. To revoke it,
use the SyftHub web interface.`,
	RunE: runLogout,
}

func init() {
	logoutCmd.Flags().BoolVar(&logoutJSONOutput, "json", false, "Output result as JSON")
}

func runLogout(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	if !cfg.HasAPIToken() {
		if logoutJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "success",
				"message": "Already logged out",
			})
		} else {
			output.Success("Already logged out")
		}
		return nil
	}

	if err := config.ClearAPITokenAndSave(); err != nil {
		if logoutJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to clear token: %v", err)
		}
		return err
	}

	if logoutJSONOutput {
		output.JSON(map[string]interface{}{
			"status":  "success",
			"message": "Logged out",
		})
	} else {
		output.Success("Logged out successfully")
	}

	return nil
}
