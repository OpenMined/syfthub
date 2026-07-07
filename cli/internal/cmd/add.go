package cmd

import (
	"github.com/spf13/cobra"
)

var addCmd = &cobra.Command{
	Use:         "add",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "Add infrastructure aliases",
	Long:        `Add infrastructure aliases for aggregators and accounting services.`,
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
	RunE: func(cmd *cobra.Command, args []string) error {
		return runAddAlias(aggregatorKind, args[0], args[1], addAggregatorDefault, addAggregatorJSONOutput)
	},
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
	RunE: func(cmd *cobra.Command, args []string) error {
		return runAddAlias(accountingKind, args[0], args[1], addAccountingDefault, addAccountingJSONOutput)
	},
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
