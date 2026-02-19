package cmd

import (
	"bufio"
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/output"
	"github.com/OpenMined/syfthub/cli-go/internal/update"
	"github.com/OpenMined/syfthub/cli-go/internal/version"
)

var (
	upgradeCheckOnly bool
	upgradeForce     bool
	upgradeYes       bool
)

var upgradeCmd = &cobra.Command{
	Use:   "upgrade",
	Short: "Check for and install CLI updates",
	Long: `Check for and install CLI updates.

Checks GitHub releases for a newer version and optionally installs it.`,
	RunE: runUpgrade,
}

func init() {
	upgradeCmd.Flags().BoolVarP(&upgradeCheckOnly, "check", "c", false, "Only check, don't install")
	upgradeCmd.Flags().BoolVarP(&upgradeForce, "force", "f", false, "Bypass 24-hour cache")
	upgradeCmd.Flags().BoolVarP(&upgradeYes, "yes", "y", false, "Skip confirmation prompt")
}

func runUpgrade(cmd *cobra.Command, args []string) error {
	output.Info("Current version: v%s", version.Version)
	output.Info("Checking for updates...")

	info, err := update.CheckForUpdates(upgradeForce)
	if err != nil {
		output.Error("Failed to check for updates: %v", err)
		return err
	}

	if info == nil {
		output.Success("You're running the latest version!")
		return nil
	}

	output.Success("New version available: v%s", info.Version)
	fmt.Printf("Release URL: %s\n", info.ReleaseURL)

	if upgradeCheckOnly {
		return nil
	}

	// Confirm installation
	if !upgradeYes {
		fmt.Print("\nDo you want to update? [y/N] ")
		reader := bufio.NewReader(os.Stdin)
		response, err := reader.ReadString('\n')
		if err != nil {
			return err
		}

		response = strings.TrimSpace(strings.ToLower(response))
		if response != "y" && response != "yes" {
			output.Info("Update cancelled.")
			return nil
		}
	}

	output.Info("Downloading v%s...", info.Version)

	success, message := update.PerformSelfUpdate(info)
	if success {
		output.Success(message)
	} else {
		output.Error(message)
		return fmt.Errorf("update failed")
	}

	return nil
}
