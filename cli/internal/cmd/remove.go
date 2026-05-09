package cmd

import (
	"github.com/spf13/cobra"
)

var removeCmd = &cobra.Command{
	Use:         "remove",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "Remove infrastructure aliases",
	Long:        `Remove infrastructure aliases for aggregators and accounting services.`,
}

// Remove aggregator subcommand
var removeAggregatorJSONOutput bool

var removeAggregatorCmd = &cobra.Command{
	Use:   "aggregator <alias>",
	Short: "Remove an aggregator alias",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runRemoveAlias(aggregatorKind, args[0], removeAggregatorJSONOutput)
	},
}

// Remove accounting subcommand
var removeAccountingJSONOutput bool

var removeAccountingCmd = &cobra.Command{
	Use:   "accounting <alias>",
	Short: "Remove an accounting service alias",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runRemoveAlias(accountingKind, args[0], removeAccountingJSONOutput)
	},
}

func init() {
	removeAggregatorCmd.Flags().BoolVar(&removeAggregatorJSONOutput, "json", false, "Output result as JSON")
	removeAccountingCmd.Flags().BoolVar(&removeAccountingJSONOutput, "json", false, "Output result as JSON")

	removeCmd.AddCommand(removeAggregatorCmd)
	removeCmd.AddCommand(removeAccountingCmd)
}
