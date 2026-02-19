// Package cmd implements all CLI commands.
package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/version"
)

var (
	// Global flags
	noUpdateCheck bool
)

// rootCmd represents the base command when called without any subcommands.
var rootCmd = &cobra.Command{
	Use:   "syft",
	Short: "SyftHub CLI - Interact with the SyftHub platform",
	Long: `SyftHub CLI - A Unix-style interface for the SyftHub platform.

Browse endpoints, query models with RAG, and manage your SyftHub configuration.`,
	SilenceUsage:  true,
	SilenceErrors: true,
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
	rootCmd.AddCommand(upgradeCmd)

	// Add command groups
	rootCmd.AddCommand(addCmd)
	rootCmd.AddCommand(listCmd)
	rootCmd.AddCommand(updateCmd)
	rootCmd.AddCommand(removeCmd)
	rootCmd.AddCommand(configCmd)
	rootCmd.AddCommand(completionCmd)
}
