package cmd

import (
	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var addCmd = &cobra.Command{
	Use:   "add",
	Short: "Add infrastructure aliases",
	Long:  `Add infrastructure aliases for aggregators and accounting services.`,
}

// Add aggregator subcommand
var (
	addAggregatorDefault    bool
	addAggregatorJSONOutput bool
)

var addAggregatorCmd = &cobra.Command{
	Use:   "aggregator <alias> <url>",
	Short: "Add an aggregator alias",
	Args:  cobra.ExactArgs(2),
	RunE:  runAddAggregator,
}

// Add accounting subcommand
var (
	addAccountingDefault    bool
	addAccountingJSONOutput bool
)

var addAccountingCmd = &cobra.Command{
	Use:   "accounting <alias> <url>",
	Short: "Add an accounting service alias",
	Args:  cobra.ExactArgs(2),
	RunE:  runAddAccounting,
}

func init() {
	// Add aggregator flags
	addAggregatorCmd.Flags().BoolVarP(&addAggregatorDefault, "default", "d", false, "Set as default aggregator")
	addAggregatorCmd.Flags().BoolVar(&addAggregatorJSONOutput, "json", false, "Output result as JSON")

	// Add accounting flags
	addAccountingCmd.Flags().BoolVarP(&addAccountingDefault, "default", "d", false, "Set as default accounting service")
	addAccountingCmd.Flags().BoolVar(&addAccountingJSONOutput, "json", false, "Output result as JSON")

	// Register subcommands
	addCmd.AddCommand(addAggregatorCmd)
	addCmd.AddCommand(addAccountingCmd)
}

func runAddAggregator(cmd *cobra.Command, args []string) error {
	alias := args[0]
	url := args[1]

	cfg := config.Load()

	if _, exists := cfg.Aggregators[alias]; exists {
		if addAggregatorJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Aggregator '" + alias + "' already exists",
			})
		} else {
			output.Error("Aggregator '%s' already exists. Use 'syft update aggregator' to modify it.", alias)
		}
		return nil
	}

	cfg.Aggregators[alias] = config.AggregatorConfig{URL: url}

	if addAggregatorDefault {
		cfg.DefaultAggregator = &alias
	}

	if err := cfg.Save(); err != nil {
		if addAggregatorJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save config: %v", err)
		}
		return err
	}

	if addAggregatorJSONOutput {
		output.JSON(map[string]interface{}{
			"status":     "success",
			"alias":      alias,
			"url":        url,
			"is_default": addAggregatorDefault,
		})
	} else {
		msg := "Added aggregator '" + alias + "' -> " + url
		if addAggregatorDefault {
			msg += " (default)"
		}
		output.Success(msg)
	}

	return nil
}

func runAddAccounting(cmd *cobra.Command, args []string) error {
	alias := args[0]
	url := args[1]

	cfg := config.Load()

	if _, exists := cfg.AccountingServices[alias]; exists {
		if addAccountingJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": "Accounting service '" + alias + "' already exists",
			})
		} else {
			output.Error("Accounting service '%s' already exists. Use 'syft update accounting' to modify it.", alias)
		}
		return nil
	}

	cfg.AccountingServices[alias] = config.AccountingConfig{URL: url}

	if addAccountingDefault {
		cfg.DefaultAccounting = &alias
	}

	if err := cfg.Save(); err != nil {
		if addAccountingJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save config: %v", err)
		}
		return err
	}

	if addAccountingJSONOutput {
		output.JSON(map[string]interface{}{
			"status":     "success",
			"alias":      alias,
			"url":        url,
			"is_default": addAccountingDefault,
		})
	} else {
		msg := "Added accounting service '" + alias + "' -> " + url
		if addAccountingDefault {
			msg += " (default)"
		}
		output.Success(msg)
	}

	return nil
}
