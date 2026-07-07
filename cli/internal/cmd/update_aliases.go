package cmd

import (
	"github.com/spf13/cobra"
)

var updateCmd = &cobra.Command{
	Use:         "update",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "Update infrastructure aliases",
	Long:        `Update infrastructure aliases for aggregators and accounting services.`,
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
	RunE: func(cmd *cobra.Command, args []string) error {
		return runUpdateAlias(aggregatorKind, args[0], updateAggregatorURL, updateAggregatorDefault, updateAggregatorJSONOutput)
	},
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
	RunE: func(cmd *cobra.Command, args []string) error {
		return runUpdateAlias(accountingKind, args[0], updateAccountingURL, updateAccountingDefault, updateAccountingJSONOutput)
	},
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
