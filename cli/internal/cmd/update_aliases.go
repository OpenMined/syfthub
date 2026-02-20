package cmd

import (
	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var updateCmd = &cobra.Command{
	Use:   "update",
	Short: "Update infrastructure aliases",
	Long:  `Update infrastructure aliases for aggregators and accounting services.`,
}

// Update aggregator subcommand
var (
	updateAggregatorURL        string
	updateAggregatorDefault    bool
	updateAggregatorJSONOutput bool
)

var updateAggregatorCmd = &cobra.Command{
	Use:   "aggregator <alias>",
	Short: "Update an aggregator alias",
	Args:  cobra.ExactArgs(1),
	RunE:  runUpdateAggregator,
}

// Update accounting subcommand
var (
	updateAccountingURL        string
	updateAccountingDefault    bool
	updateAccountingJSONOutput bool
)

var updateAccountingCmd = &cobra.Command{
	Use:   "accounting <alias>",
	Short: "Update an accounting service alias",
	Args:  cobra.ExactArgs(1),
	RunE:  runUpdateAccounting,
}

func init() {
	// Update aggregator flags
	updateAggregatorCmd.Flags().StringVarP(&updateAggregatorURL, "url", "u", "", "New URL for the aggregator")
	updateAggregatorCmd.Flags().BoolVarP(&updateAggregatorDefault, "default", "d", false, "Set as default aggregator")
	updateAggregatorCmd.Flags().BoolVar(&updateAggregatorJSONOutput, "json", false, "Output result as JSON")

	// Update accounting flags
	updateAccountingCmd.Flags().StringVarP(&updateAccountingURL, "url", "u", "", "New URL for the accounting service")
	updateAccountingCmd.Flags().BoolVarP(&updateAccountingDefault, "default", "d", false, "Set as default accounting service")
	updateAccountingCmd.Flags().BoolVar(&updateAccountingJSONOutput, "json", false, "Output result as JSON")

	// Register subcommands
	updateCmd.AddCommand(updateAggregatorCmd)
	updateCmd.AddCommand(updateAccountingCmd)
}

func runUpdateAggregator(cmd *cobra.Command, args []string) error {
	alias := args[0]

	cfg := config.Load()

	if _, exists := cfg.Aggregators[alias]; !exists {
		if updateAggregatorJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Aggregator '" + alias + "' not found",
			})
		} else {
			output.Error("Aggregator '%s' not found.", alias)
		}
		return nil
	}

	if updateAggregatorURL == "" && !updateAggregatorDefault {
		if updateAggregatorJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Nothing to update",
			})
		} else {
			output.Warning("Nothing to update. Specify --url or --default.")
		}
		return nil
	}

	if updateAggregatorURL != "" {
		cfg.Aggregators[alias] = config.AggregatorConfig{URL: updateAggregatorURL}
	}

	if updateAggregatorDefault {
		cfg.DefaultAggregator = &alias
	}

	if err := cfg.Save(); err != nil {
		if updateAggregatorJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save config: %v", err)
		}
		return err
	}

	isDefault := cfg.DefaultAggregator != nil && *cfg.DefaultAggregator == alias

	if updateAggregatorJSONOutput {
		output.JSON(map[string]interface{}{
			"status":     "success",
			"alias":      alias,
			"url":        cfg.Aggregators[alias].URL,
			"is_default": isDefault,
		})
	} else {
		output.Success("Updated aggregator '%s'", alias)
	}

	return nil
}

func runUpdateAccounting(cmd *cobra.Command, args []string) error {
	alias := args[0]

	cfg := config.Load()

	if _, exists := cfg.AccountingServices[alias]; !exists {
		if updateAccountingJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Accounting service '" + alias + "' not found",
			})
		} else {
			output.Error("Accounting service '%s' not found.", alias)
		}
		return nil
	}

	if updateAccountingURL == "" && !updateAccountingDefault {
		if updateAccountingJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Nothing to update",
			})
		} else {
			output.Warning("Nothing to update. Specify --url or --default.")
		}
		return nil
	}

	if updateAccountingURL != "" {
		cfg.AccountingServices[alias] = config.AccountingConfig{URL: updateAccountingURL}
	}

	if updateAccountingDefault {
		cfg.DefaultAccounting = &alias
	}

	if err := cfg.Save(); err != nil {
		if updateAccountingJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save config: %v", err)
		}
		return err
	}

	isDefault := cfg.DefaultAccounting != nil && *cfg.DefaultAccounting == alias

	if updateAccountingJSONOutput {
		output.JSON(map[string]interface{}{
			"status":     "success",
			"alias":      alias,
			"url":        cfg.AccountingServices[alias].URL,
			"is_default": isDefault,
		})
	} else {
		output.Success("Updated accounting service '%s'", alias)
	}

	return nil
}
