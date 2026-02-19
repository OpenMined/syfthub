package cmd

import (
	"sort"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/config"
	"github.com/OpenMined/syfthub/cli-go/internal/output"
)

var listCmd = &cobra.Command{
	Use:   "list",
	Short: "List infrastructure aliases",
	Long:  `List infrastructure aliases for aggregators and accounting services.`,
}

// List aggregator subcommand
var listAggregatorJSONOutput bool

var listAggregatorCmd = &cobra.Command{
	Use:   "aggregator",
	Short: "List aggregator aliases",
	RunE:  runListAggregator,
}

// List accounting subcommand
var listAccountingJSONOutput bool

var listAccountingCmd = &cobra.Command{
	Use:   "accounting",
	Short: "List accounting service aliases",
	RunE:  runListAccounting,
}

func init() {
	listAggregatorCmd.Flags().BoolVar(&listAggregatorJSONOutput, "json", false, "Output result as JSON")
	listAccountingCmd.Flags().BoolVar(&listAccountingJSONOutput, "json", false, "Output result as JSON")

	listCmd.AddCommand(listAggregatorCmd)
	listCmd.AddCommand(listAccountingCmd)
}

func runListAggregator(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	if listAggregatorJSONOutput {
		result := make(map[string]interface{})
		for alias, agg := range cfg.Aggregators {
			isDefault := cfg.DefaultAggregator != nil && *cfg.DefaultAggregator == alias
			result[alias] = map[string]interface{}{
				"url":        agg.URL,
				"is_default": isDefault,
			}
		}
		output.JSON(map[string]interface{}{
			"status":      "success",
			"aggregators": result,
		})
	} else {
		aliases := make([]output.AliasInfo, 0, len(cfg.Aggregators))
		for alias, agg := range cfg.Aggregators {
			isDefault := cfg.DefaultAggregator != nil && *cfg.DefaultAggregator == alias
			aliases = append(aliases, output.AliasInfo{
				Name:      alias,
				URL:       agg.URL,
				IsDefault: isDefault,
			})
		}
		sort.Slice(aliases, func(i, j int) bool {
			return aliases[i].Name < aliases[j].Name
		})
		output.PrintAliasesTable(aliases, "Aggregator")
	}

	return nil
}

func runListAccounting(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	if listAccountingJSONOutput {
		result := make(map[string]interface{})
		for alias, acc := range cfg.AccountingServices {
			isDefault := cfg.DefaultAccounting != nil && *cfg.DefaultAccounting == alias
			result[alias] = map[string]interface{}{
				"url":        acc.URL,
				"is_default": isDefault,
			}
		}
		output.JSON(map[string]interface{}{
			"status":              "success",
			"accounting_services": result,
		})
	} else {
		aliases := make([]output.AliasInfo, 0, len(cfg.AccountingServices))
		for alias, acc := range cfg.AccountingServices {
			isDefault := cfg.DefaultAccounting != nil && *cfg.DefaultAccounting == alias
			aliases = append(aliases, output.AliasInfo{
				Name:      alias,
				URL:       acc.URL,
				IsDefault: isDefault,
			})
		}
		sort.Slice(aliases, func(i, j int) bool {
			return aliases[i].Name < aliases[j].Name
		})
		output.PrintAliasesTable(aliases, "Accounting")
	}

	return nil
}
