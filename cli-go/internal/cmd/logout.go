package cmd

import (
	"context"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/config"
	"github.com/OpenMined/syfthub/cli-go/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var logoutJSONOutput bool

var logoutCmd = &cobra.Command{
	Use:   "logout",
	Short: "Clear authentication credentials",
	Long: `Clear authentication credentials.

Removes stored tokens from the local configuration and invalidates them on the server.`,
	RunE: runLogout,
}

func init() {
	logoutCmd.Flags().BoolVar(&logoutJSONOutput, "json", false, "Output result as JSON")
}

func runLogout(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	if !cfg.HasTokens() {
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

	// Try to logout on server if we have tokens
	if cfg.AccessToken != nil && *cfg.AccessToken != "" {
		func() {
			client, err := syfthub.NewClient(
				syfthub.WithBaseURL(cfg.HubURL),
				syfthub.WithTimeout(time.Duration(cfg.Timeout)*time.Second),
			)
			if err != nil {
				return
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

			// Try server logout - ignore errors
			ctx := context.Background()
			client.Logout(ctx)
		}()
	}

	// Clear local tokens
	if err := config.ClearTokensAndSave(); err != nil {
		if logoutJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to clear tokens: %v", err)
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
