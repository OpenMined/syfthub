package cmd

import (
	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var removeCmd = &cobra.Command{
	Use:   "remove",
	Short: "Remove infrastructure aliases",
	Long:  `Remove infrastructure aliases for aggregators and accounting services.`,
}

// Remove aggregator subcommand
var removeAggregatorJSONOutput bool

var removeAggregatorCmd = &cobra.Command{
	Use:   "aggregator <alias>",
	Short: "Remove an aggregator alias",
	Args:  cobra.ExactArgs(1),
	RunE:  runRemoveAggregator,
}

// Remove accounting subcommand
var removeAccountingJSONOutput bool

var removeAccountingCmd = &cobra.Command{
	Use:   "accounting <alias>",
	Short: "Remove an accounting service alias",
	Args:  cobra.ExactArgs(1),
	RunE:  runRemoveAccounting,
}

func init() {
	removeAggregatorCmd.Flags().BoolVar(&removeAggregatorJSONOutput, "json", false, "Output result as JSON")
	removeAccountingCmd.Flags().BoolVar(&removeAccountingJSONOutput, "json", false, "Output result as JSON")

	removeCmd.AddCommand(removeAggregatorCmd)
	removeCmd.AddCommand(removeAccountingCmd)
}

func runRemoveAggregator(cmd *cobra.Command, args []string) error {
	alias := args[0]

	cfg := config.Load()

	if _, exists := cfg.Aggregators[alias]; !exists {
		if removeAggregatorJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Aggregator '" + alias + "' not found",
			})
		} else {
			output.Error("Aggregator '%s' not found.", alias)
		}
		return nil
	}

	delete(cfg.Aggregators, alias)

	// Clear default if it was this alias
	if cfg.DefaultAggregator != nil && *cfg.DefaultAggregator == alias {
		cfg.DefaultAggregator = nil
	}

	if err := cfg.Save(); err != nil {
		if removeAggregatorJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save config: %v", err)
		}
		return err
	}

	if removeAggregatorJSONOutput {
		output.JSON(map[string]interface{}{
			"status":  "success",
			"alias":   alias,
			"message": "Removed",
		})
	} else {
		output.Success("Removed aggregator '%s'", alias)
	}

	return nil
}

func runRemoveAccounting(cmd *cobra.Command, args []string) error {
	alias := args[0]

	cfg := config.Load()

	if _, exists := cfg.AccountingServices[alias]; !exists {
		if removeAccountingJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Accounting service '" + alias + "' not found",
			})
		} else {
			output.Error("Accounting service '%s' not found.", alias)
		}
		return nil
	}

	delete(cfg.AccountingServices, alias)

	// Clear default if it was this alias
	if cfg.DefaultAccounting != nil && *cfg.DefaultAccounting == alias {
		cfg.DefaultAccounting = nil
	}

	if err := cfg.Save(); err != nil {
		if removeAccountingJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save config: %v", err)
		}
		return err
	}

	if removeAccountingJSONOutput {
		output.JSON(map[string]interface{}{
			"status":  "success",
			"alias":   alias,
			"message": "Removed",
		})
	} else {
		output.Success("Removed accounting service '%s'", alias)
	}

	return nil
}
