package cmd

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli-go/internal/config"
	"github.com/OpenMined/syfthub/cli-go/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	loginUsername   string
	loginPassword   string
	loginJSONOutput bool
)

var loginCmd = &cobra.Command{
	Use:   "login",
	Short: "Authenticate with SyftHub",
	Long: `Authenticate with SyftHub.

Prompts for username and password if not provided via options.`,
	RunE: runLogin,
}

func init() {
	loginCmd.Flags().StringVarP(&loginUsername, "username", "u", "", "Username for authentication")
	loginCmd.Flags().StringVarP(&loginPassword, "password", "p", "", "Password for authentication")
	loginCmd.Flags().BoolVar(&loginJSONOutput, "json", false, "Output result as JSON")
}

func runLogin(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	// Prompt for credentials if not provided
	username := loginUsername
	password := loginPassword

	if username == "" {
		fmt.Print("Username: ")
		reader := bufio.NewReader(os.Stdin)
		input, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read username: %w", err)
		}
		username = strings.TrimSpace(input)
	}

	if password == "" {
		fmt.Print("Password: ")
		bytePassword, err := term.ReadPassword(int(syscall.Stdin))
		if err != nil {
			return fmt.Errorf("failed to read password: %w", err)
		}
		fmt.Println() // Print newline after password input
		password = string(bytePassword)
	}

	// Create client
	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout)*time.Second),
	)
	if err != nil {
		if loginJSONOutput {
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

	// Login
	ctx := context.Background()
	user, err := client.Login(ctx, username, password)
	if err != nil {
		if loginJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Authentication failed: %v", err)
		}
		return err
	}

	// Store tokens in config
	tokens := client.GetTokens()
	if tokens != nil {
		cfg.SetTokens(tokens.AccessToken, tokens.RefreshToken)
		if err := cfg.Save(); err != nil {
			if loginJSONOutput {
				output.JSON(map[string]interface{}{
					"status":  "error",
					"message": fmt.Sprintf("Failed to save tokens: %v", err),
				})
			} else {
				output.Error("Failed to save tokens: %v", err)
			}
			return err
		}
	}

	if loginJSONOutput {
		output.JSON(map[string]interface{}{
			"status":   "success",
			"username": user.Username,
			"email":    user.Email,
		})
	} else {
		output.Success("Logged in as %s", user.Username)
	}

	return nil
}
