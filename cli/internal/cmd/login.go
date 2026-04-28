package cmd

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/clientutil"
	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	loginToken      string
	loginJSONOutput bool
)

var loginCmd = &cobra.Command{
	Use:         "login",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "Authenticate with SyftHub using an API token",
	Long: `Authenticate with SyftHub using a Personal Access Token (PAT).

Provide your API token via --token flag or enter it interactively.
You can generate a PAT from your SyftHub account settings.`,
	RunE: runLogin,
}

func init() {
	loginCmd.Flags().StringVarP(&loginToken, "token", "t", "", "API token (PAT)")
	loginCmd.Flags().BoolVar(&loginJSONOutput, "json", false, "Output result as JSON")
}

func runLogin(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	token := loginToken

	// Prompt for token if not provided
	if token == "" {
		if term.IsTerminal(int(os.Stdin.Fd())) {
			fmt.Print("API Token: ")
			byteToken, err := term.ReadPassword(int(os.Stdin.Fd()))
			if err != nil {
				return fmt.Errorf("failed to read token: %w", err)
			}
			fmt.Println()
			token = strings.TrimSpace(string(byteToken))
		} else {
			reader := bufio.NewReader(os.Stdin)
			line, err := reader.ReadString('\n')
			if err != nil {
				return fmt.Errorf("failed to read token from stdin: %w", err)
			}
			token = strings.TrimSpace(line)
		}
	}

	if token == "" {
		msg := "API token is required"
		if loginJSONOutput {
			output.JSON(map[string]any{"status": output.StatusError, "message": msg})
		} else {
			output.Error(msg)
		}
		return fmt.Errorf("%s", msg)
	}

	// Validate the token by calling /auth/me
	client, err := clientutil.NewClient(cfg, "", 0, syfthub.WithAPIToken(token))
	if err != nil {
		return output.ReplyError(loginJSONOutput, "Failed to create client: %v", err)
	}
	defer client.Close()

	ctx := context.Background()
	user, err := client.Me(ctx)
	if err != nil {
		if loginJSONOutput {
			output.JSON(map[string]any{"status": output.StatusError, "message": "Invalid API token"})
		} else {
			output.Error("Invalid API token: %v", err)
		}
		return err
	}

	// Store token in config
	cfg.SetAPIToken(token)
	if err := cfg.Save(); err != nil {
		return output.ReplyError(loginJSONOutput, "Failed to save token: %v", err)
	}

	output.ReplySuccess(loginJSONOutput, map[string]any{
		"username": user.Username,
		"email":    user.Email,
	}, "Logged in as %s", user.Username)

	return nil
}
