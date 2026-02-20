package cmd

import (
	"context"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
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

	if !cfg.HasTokens() {
		if whoamiJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Not logged in",
			})
		} else {
			output.Error("Not logged in. Use 'syft login' to authenticate.")
		}
		return fmt.Errorf("not logged in")
	}

	// Create client
	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout)*time.Second),
	)
	if err != nil {
		if whoamiJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to create client: %v", err)
		}
		return err
	}
	defer client.Close()

	// Set tokens
	refreshToken := ""
	if cfg.RefreshToken != nil {
		refreshToken = *cfg.RefreshToken
	}
	client.SetTokens(&syfthub.AuthTokens{
		AccessToken:  *cfg.AccessToken,
		RefreshToken: refreshToken,
	})

	// Get current user
	ctx := context.Background()
	user, err := client.Me(ctx)
	if err != nil {
		if whoamiJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to get user info: %v", err)
		}
		return err
	}

	if whoamiJSONOutput {
		output.JSON(map[string]interface{}{
			"status": "success",
			"user": map[string]interface{}{
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
