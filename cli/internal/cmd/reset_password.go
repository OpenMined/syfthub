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
	resetPasswordEmail       string
	resetPasswordCode        string
	resetPasswordNewPassword string
	resetPasswordJSONOutput  bool
)

var resetPasswordCmd = &cobra.Command{
	Use:   "reset-password",
	Short: "Reset your password via email OTP",
	Long: `Reset your password via email OTP.

This is a two-step process:
1. Request a reset code (sent to your email)
2. Enter the code and your new password

If all flags are provided, the interactive prompts are skipped.`,
	RunE: runResetPassword,
}

func init() {
	resetPasswordCmd.Flags().StringVarP(&resetPasswordEmail, "email", "e", "", "Email address")
	resetPasswordCmd.Flags().StringVarP(&resetPasswordCode, "code", "c", "", "6-digit reset code (skip request step)")
	resetPasswordCmd.Flags().StringVar(&resetPasswordNewPassword, "new-password", "", "New password")
	resetPasswordCmd.Flags().BoolVar(&resetPasswordJSONOutput, "json", false, "Output result as JSON")
}

func runResetPassword(cmd *cobra.Command, args []string) error {
	cfg := config.Load()
	reader := bufio.NewReader(os.Stdin)

	// Create client
	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout)*time.Second),
	)
	if err != nil {
		if resetPasswordJSONOutput {
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

	ctx := context.Background()

	// Step 1: Get email
	if resetPasswordEmail == "" {
		fmt.Print("Email: ")
		input, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read email: %w", err)
		}
		resetPasswordEmail = strings.TrimSpace(input)
	}

	// Step 2: Request reset code (skip if code already provided)
	if resetPasswordCode == "" {
		err := client.Auth.RequestPasswordReset(ctx, resetPasswordEmail)
		if err != nil {
			if resetPasswordJSONOutput {
				output.JSON(map[string]interface{}{
					"status":  "error",
					"message": err.Error(),
				})
			} else {
				output.Error("Failed to request password reset: %v", err)
			}
			return err
		}

		if resetPasswordJSONOutput {
			// In JSON/scriptable mode with no code, just report that the code was sent
			output.JSON(map[string]interface{}{
				"status":  "code_sent",
				"email":   resetPasswordEmail,
				"message": "Reset code sent. Re-run with --code and --new-password flags.",
			})
			return nil
		}

		output.Info("A reset code has been sent to %s", resetPasswordEmail)

		fmt.Print("Enter the 6-digit code: ")
		codeInput, err := reader.ReadString('\n')
		if err != nil {
			return fmt.Errorf("failed to read code: %w", err)
		}
		resetPasswordCode = strings.TrimSpace(codeInput)
	}

	// Step 3: Get new password
	if resetPasswordNewPassword == "" {
		fmt.Print("New password: ")
		bytePassword, err := term.ReadPassword(int(syscall.Stdin))
		if err != nil {
			return fmt.Errorf("failed to read password: %w", err)
		}
		fmt.Println()
		resetPasswordNewPassword = string(bytePassword)
	}

	// Step 4: Confirm password reset
	err = client.Auth.ConfirmPasswordReset(ctx, &syfthub.PasswordResetConfirmRequest{
		Email:       resetPasswordEmail,
		Code:        resetPasswordCode,
		NewPassword: resetPasswordNewPassword,
	})
	if err != nil {
		if resetPasswordJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Password reset failed: %v", err)
		}
		return err
	}

	if resetPasswordJSONOutput {
		output.JSON(map[string]interface{}{
			"status":  "success",
			"message": "Password has been reset",
		})
	} else {
		output.Success("Password has been reset. You can now login with your new password.")
	}

	return nil
}
