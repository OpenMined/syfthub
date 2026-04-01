// Package cmd implements all CLI commands.
package cmd

import (
	"context"
	"errors"
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/OpenMined/syfthub/cli/internal/version"
)

// authExemptKey is the cobra Annotations key used to mark a command (and its
// subcommands) as not requiring authentication.
const authExemptKey = "auth-exempt"

var (
	// Global flags
	noUpdateCheck bool
)

// isAuthExempt reports whether cmd or any of its ancestors is marked with the
// auth-exempt annotation, meaning the command does not require authentication.
func isAuthExempt(cmd *cobra.Command) bool {
	for c := cmd; c != nil; c = c.Parent() {
		if c.Annotations[authExemptKey] == "true" {
			return true
		}
	}
	return false
}

// ensureAuthenticated is the PersistentPreRunE hook attached to rootCmd.
// It opens the browser for authentication whenever a command is run without an
// API token configured, giving users a seamless first-run experience.
func ensureAuthenticated(cmd *cobra.Command, _ []string) error {
	if isAuthExempt(cmd) {
		return nil
	}

	if f := cmd.Flags().Lookup("api-key"); f != nil && f.Changed {
		return nil
	}

	cfg := nodeconfig.Load()

	if cfg.HasAPIToken() {
		return nil
	}

	// Non-interactive environments (CI, pipes, --json): skip browser, let the
	// command produce its own "authentication required" error.
	jsonFlag := cmd.Flags().Lookup("json")
	isJSON := jsonFlag != nil && jsonFlag.Changed
	if isJSON || !term.IsTerminal(int(os.Stdin.Fd())) {
		return nil
	}

	output.Info("Authentication required.")
	token, err := startBrowserAuthFlow(cmd.Context(), cfg.HubURL, func(setupURL string) {
		output.Info("Opening SyftHub in your browser...")
		fmt.Printf("\n  %s\n\n", setupURL)
		fmt.Println("  Can't open the browser? Paste the URL above into your browser manually.")
		fmt.Println("  Waiting... (Ctrl+C to cancel and enter a token manually)")
		fmt.Println()
	})

	switch {
	case err == nil:
		cfg.APIToken = token
		var saveErr error
		if saveErr = nodeconfig.EnsureConfigDir(); saveErr == nil {
			saveErr = cfg.Save()
		}
		if saveErr != nil {
			output.Warning("Token could not be saved to config (%v). You may need to sign in again next time.", saveErr)
		}
		output.Success("Signed in! Continuing...")
		fmt.Println()

	case errors.Is(err, context.Canceled):
		fmt.Println()
		output.Info("Browser sign-in cancelled.")
		fmt.Println()
		// Return nil so the command can produce its own auth error or
		// fall back to its own prompting (e.g. syft node init).

	default:
		fmt.Println()
		output.Warning("Browser sign-in did not complete (%v).", err)
		fmt.Println()
		// Return nil; the command will handle missing auth in its own RunE.
	}

	return nil
}

// rootCmd represents the base command when called without any subcommands.
var rootCmd = &cobra.Command{
	Use:   "syft",
	Short: "SyftHub CLI - Interact with the SyftHub platform",
	Long: `SyftHub CLI - A Unix-style interface for the SyftHub platform.

Browse endpoints, query models with RAG, and manage your SyftHub configuration.`,
	SilenceUsage:      true,
	SilenceErrors:     true,
	PersistentPreRunE: ensureAuthenticated,
}

// Execute adds all child commands to the root command and sets flags appropriately.
func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func init() {
	// Version flag
	rootCmd.Version = version.Version
	rootCmd.SetVersionTemplate("syft version {{.Version}}\n")

	// Hidden flag to disable update check
	rootCmd.PersistentFlags().BoolVar(&noUpdateCheck, "no-update-check", false, "Disable update check notification")
	rootCmd.PersistentFlags().MarkHidden("no-update-check")

	// Add all subcommands
	rootCmd.AddCommand(loginCmd)
	rootCmd.AddCommand(logoutCmd)
	rootCmd.AddCommand(whoamiCmd)
	rootCmd.AddCommand(lsCmd)
	rootCmd.AddCommand(queryCmd)
	rootCmd.AddCommand(agentCmd)
	rootCmd.AddCommand(upgradeCmd)

	// Add command groups
	rootCmd.AddCommand(addCmd)
	rootCmd.AddCommand(listCmd)
	rootCmd.AddCommand(updateCmd)
	rootCmd.AddCommand(removeCmd)
	rootCmd.AddCommand(configCmd)
	rootCmd.AddCommand(completionCmd)
	rootCmd.AddCommand(nodeCmd)
}
