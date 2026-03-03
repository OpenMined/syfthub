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

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	registerUsername   string
	registerEmail      string
	registerPassword   string
	registerFullName   string
	registerJSONOutput bool
)

var registerCmd = &cobra.Command{
	Use:   "register",
	Short: "Register a new SyftHub account",
	Long: `Register a new SyftHub account.

Prompts for details if not provided via flags. If the platform requires
email verification, you will be prompted for the OTP code sent to your email.`,
	RunE: runRegister,
}

func init() {
	registerCmd.Flags().StringVarP(&registerUsername, "username", "u", "", "Username for the new account")
	registerCmd.Flags().StringVarP(&registerEmail, "email", "e", "", "Email address")
	registerCmd.Flags().StringVarP(&registerPassword, "password", "p", "", "Password")
	registerCmd.Flags().StringVar(&registerFullName, "full-name", "", "Full name")
	registerCmd.Flags().BoolVar(&registerJSONOutput, "json", false, "Output result as JSON")
}

func runRegister(cmd *cobra.Command, args []string) error {
	cfg := config.Load()
	reader := bufio.NewReader(os.Stdin)

	// Prompt for missing fields
	if registerFullName == "" {
		fmt.Print("Full Name: ")
		input, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read full name: %w", err)
		}
		registerFullName = strings.TrimSpace(input)
	}

	if registerEmail == "" {
		fmt.Print("Email: ")
		input, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read email: %w", err)
		}
		registerEmail = strings.TrimSpace(input)
	}

	if registerUsername == "" {
		// Generate default from email
		defaultUsername := strings.Split(registerEmail, "@")[0]
		fmt.Printf("Username [%s]: ", defaultUsername)
		input, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read username: %w", err)
		}
		registerUsername = strings.TrimSpace(input)
		if registerUsername == "" {
			registerUsername = defaultUsername
		}
	}

	if registerPassword == "" {
		fmt.Print("Password: ")
		bytePassword, err := term.ReadPassword(int(syscall.Stdin))
		if err != nil {
			return fmt.Errorf("failed to read password: %w", err)
		}
		fmt.Println()
		registerPassword = string(bytePassword)
	}

	// Create client
	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout)*time.Second),
	)
	if err != nil {
		if registerJSONOutput {
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

	// Register
	ctx := context.Background()
	result, err := client.Auth.Register(ctx, &syfthub.RegisterRequest{
		Username: registerUsername,
		Email:    registerEmail,
		Password: registerPassword,
		FullName: registerFullName,
	})
	if err != nil {
		if registerJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Registration failed: %v", err)
		}
		return err
	}

	// Handle email verification if required
	if result.RequiresEmailVerification {
		if registerJSONOutput {
			output.JSON(map[string]interface{}{
				"status":                      "verification_required",
				"email":                       registerEmail,
				"requires_email_verification": true,
			})
			// In JSON mode, don't prompt interactively — user should use verify-email command
			return nil
		}

		output.Info("A verification code has been sent to %s", registerEmail)
		fmt.Print("Enter the 6-digit code: ")
		codeInput, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read verification code: %w", err)
		}
		code := strings.TrimSpace(codeInput)

		user, err := client.Auth.VerifyOTP(ctx, &syfthub.VerifyOTPRequest{
			Email: registerEmail,
			Code:  code,
		})
		if err != nil {
			output.Error("Verification failed: %v", err)
			output.Info("You can retry with: syft verify-email --email %s", registerEmail)
			return err
		}

		// Store tokens
		tokens := client.GetTokens()
		if tokens != nil {
			cfg.SetTokens(tokens.AccessToken, tokens.RefreshToken)
			if saveErr := cfg.Save(); saveErr != nil {
				output.Error("Failed to save tokens: %v", saveErr)
				return saveErr
			}
		}

		output.Success("Registered and verified as %s", user.Username)
		return nil
	}

	// No verification needed — store tokens directly
	tokens := client.GetTokens()
	if tokens != nil {
		cfg.SetTokens(tokens.AccessToken, tokens.RefreshToken)
		if saveErr := cfg.Save(); saveErr != nil {
			if registerJSONOutput {
				output.JSON(map[string]interface{}{
					"status":  "error",
					"message": fmt.Sprintf("Failed to save tokens: %v", saveErr),
				})
			} else {
				output.Error("Failed to save tokens: %v", saveErr)
			}
			return saveErr
		}
	}

	if registerJSONOutput {
		output.JSON(map[string]interface{}{
			"status":   "success",
			"username": result.User.Username,
			"email":    result.User.Email,
		})
	} else {
		output.Success("Registered as %s", result.User.Username)
	}

	return nil
}
