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
		output.ReplySuccess(logoutJSONOutput, map[string]any{"message": "Already logged out"}, "Already logged out")
		return nil
	}

	if err := config.ClearAPITokenAndSave(); err != nil {
		return output.ReplyError(logoutJSONOutput, "Failed to clear token: %v", err)
	}

	output.ReplySuccess(logoutJSONOutput, map[string]any{"message": "Logged out"}, "Logged out successfully")

	return nil
}
