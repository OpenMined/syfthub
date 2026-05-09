package cmd

import (
	"github.com/spf13/cobra"
)

var listCmd = &cobra.Command{
	Use:         "list",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "List infrastructure aliases",
	Long:        `List infrastructure aliases for aggregators and accounting services.`,
}

// List aggregator subcommand
var listAggregatorJSONOutput bool

var listAggregatorCmd = &cobra.Command{
	Use:   "aggregator",
	Short: "List aggregator aliases",
	RunE: func(cmd *cobra.Command, args []string) error {
		return runListAlias(aggregatorKind, listAggregatorJSONOutput)
	},
}

// List accounting subcommand
var listAccountingJSONOutput bool

var listAccountingCmd = &cobra.Command{
	Use:   "accounting",
	Short: "List accounting service aliases",
	RunE: func(cmd *cobra.Command, args []string) error {
		return runListAlias(accountingKind, listAccountingJSONOutput)
	},
}

func init() {
	listAggregatorCmd.Flags().BoolVar(&listAggregatorJSONOutput, "json", false, "Output result as JSON")
	listAccountingCmd.Flags().BoolVar(&listAccountingJSONOutput, "json", false, "Output result as JSON")

	listCmd.AddCommand(listAggregatorCmd)
	listCmd.AddCommand(listAccountingCmd)
}
