package cmd

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	verifyEmailAddress    string
	verifyEmailCode       string
	verifyEmailJSONOutput bool
)

var verifyEmailCmd = &cobra.Command{
	Use:   "verify-email",
	Short: "Verify your email address with an OTP code",
	Long: `Verify your email address with an OTP code.

Use this command if you registered but didn't complete email verification,
for example if you closed your terminal during registration.`,
	RunE: runVerifyEmail,
}

func init() {
	verifyEmailCmd.Flags().StringVarP(&verifyEmailAddress, "email", "e", "", "Email address to verify")
	verifyEmailCmd.Flags().StringVarP(&verifyEmailCode, "code", "c", "", "6-digit verification code")
	verifyEmailCmd.Flags().BoolVar(&verifyEmailJSONOutput, "json", false, "Output result as JSON")
}

func runVerifyEmail(cmd *cobra.Command, args []string) error {
	cfg := config.Load()
	reader := bufio.NewReader(os.Stdin)

	// Prompt for missing fields
	if verifyEmailAddress == "" {
		fmt.Print("Email: ")
		input, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read email: %w", err)
		}
		verifyEmailAddress = strings.TrimSpace(input)
	}

	if verifyEmailCode == "" {
		fmt.Print("Verification code: ")
		input, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read code: %w", err)
		}
		verifyEmailCode = strings.TrimSpace(input)
	}

	// Create client
	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout)*time.Second),
	)
	if err != nil {
		if verifyEmailJSONOutput {
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

	// Verify OTP
	ctx := context.Background()
	user, err := client.Auth.VerifyOTP(ctx, &syfthub.VerifyOTPRequest{
		Email: verifyEmailAddress,
		Code:  verifyEmailCode,
	})
	if err != nil {
		if verifyEmailJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Verification failed: %v", err)
		}
		return err
	}

	// Store tokens
	tokens := client.GetTokens()
	if tokens != nil {
		cfg.SetTokens(tokens.AccessToken, tokens.RefreshToken)
		if saveErr := cfg.Save(); saveErr != nil {
			if verifyEmailJSONOutput {
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

	if verifyEmailJSONOutput {
		output.JSON(map[string]interface{}{
			"status":   "success",
			"username": user.Username,
			"email":    user.Email,
		})
	} else {
		output.Success("Email verified! Logged in as %s", user.Username)
	}

	return nil
}
