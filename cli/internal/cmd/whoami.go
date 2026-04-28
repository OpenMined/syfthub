package cmd

import (
	"context"
	"fmt"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/clientutil"
	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var whoamiJSONOutput bool

var whoamiCmd = &cobra.Command{
	Use:   "whoami",
	Short: "Show current authenticated user",
	Long: `Show current authenticated user.

Displays the username and email of the currently logged-in user.`,
	RunE: runWhoami,
}

func init() {
	whoamiCmd.Flags().BoolVar(&whoamiJSONOutput, "json", false, "Output result as JSON")
}

func runWhoami(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	if !cfg.HasAPIToken() {
		if whoamiJSONOutput {
			output.JSON(map[string]any{
				"status":  output.StatusError,
				"message": "Not logged in",
			})
		} else {
			output.Error("Not logged in. Use 'syft login' to authenticate.")
		}
		return fmt.Errorf("not logged in")
	}

	client, err := clientutil.NewClient(cfg, "", 0)
	if err != nil {
		return output.ReplyError(whoamiJSONOutput, "Failed to create client: %v", err)
	}
	defer client.Close()

	ctx := context.Background()
	user, err := client.Me(ctx)
	if err != nil {
		return output.ReplyError(whoamiJSONOutput, "Failed to get user info: %v", err)
	}

	if whoamiJSONOutput {
		output.JSON(map[string]any{
			"status": output.StatusSuccess,
			"user": map[string]any{
				"id":       fmt.Sprintf("%d", user.ID),
				"username": user.Username,
				"email":    user.Email,
			},
		})
	} else {
		output.Cyan.Println(user.Username)
		output.Dim.Print("Email: ")
		fmt.Println(user.Email)
		output.Dim.Print("ID: ")
		fmt.Println(user.ID)
	}

	return nil
}
