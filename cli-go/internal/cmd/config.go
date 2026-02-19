package cmd

import (
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/config"
	"github.com/OpenMined/syfthub/cli-go/internal/output"
)

// Allowed configuration keys for 'config set'
var allowedKeys = map[string]string{
	"default_aggregator": "Default aggregator alias",
	"default_accounting": "Default accounting service alias",
	"timeout":            "Request timeout in seconds",
	"hub_url":            "SyftHub API URL",
}

var configCmd = &cobra.Command{
	Use:   "config",
	Short: "Manage CLI configuration",
	Long:  `Manage CLI configuration settings.`,
}

// Config set subcommand
var configSetJSONOutput bool

var configSetCmd = &cobra.Command{
	Use:   "set <key> <value>",
	Short: "Set a configuration value",
	Long:  fmt.Sprintf("Set a configuration value.\n\nAllowed keys: %s", strings.Join(getAllowedKeys(), ", ")),
	Args:  cobra.ExactArgs(2),
	RunE:  runConfigSet,
}

// Config show subcommand
var configShowJSONOutput bool

var configShowCmd = &cobra.Command{
	Use:   "show",
	Short: "Display current configuration",
	RunE:  runConfigShow,
}

// Config path subcommand
var configPathJSONOutput bool

var configPathCmd = &cobra.Command{
	Use:   "path",
	Short: "Show the configuration file path",
	RunE:  runConfigPath,
}

func init() {
	configSetCmd.Flags().BoolVar(&configSetJSONOutput, "json", false, "Output result as JSON")
	configShowCmd.Flags().BoolVar(&configShowJSONOutput, "json", false, "Output result as JSON")
	configPathCmd.Flags().BoolVar(&configPathJSONOutput, "json", false, "Output result as JSON")

	configCmd.AddCommand(configSetCmd)
	configCmd.AddCommand(configShowCmd)
	configCmd.AddCommand(configPathCmd)
}

func getAllowedKeys() []string {
	keys := make([]string, 0, len(allowedKeys))
	for k := range allowedKeys {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func runConfigSet(cmd *cobra.Command, args []string) error {
	key := args[0]
	value := args[1]

	if _, ok := allowedKeys[key]; !ok {
		if configSetJSONOutput {
			output.JSON(map[string]interface{}{
				"status":       "error",
				"message":      fmt.Sprintf("Unknown key '%s'", key),
				"allowed_keys": getAllowedKeys(),
			})
		} else {
			output.Error("Unknown key '%s'. Allowed keys: %s", key, strings.Join(getAllowedKeys(), ", "))
		}
		return nil
	}

	cfg := config.Load()

	var typedValue interface{}

	switch key {
	case "timeout":
		timeout, err := strconv.ParseFloat(value, 64)
		if err != nil {
			if configSetJSONOutput {
				output.JSON(map[string]interface{}{
					"status":  "error",
					"message": fmt.Sprintf("Invalid timeout value: %s", value),
				})
			} else {
				output.Error("Invalid timeout value: %s. Must be a number.", value)
			}
			return nil
		}
		cfg.Timeout = timeout
		typedValue = timeout

	case "default_aggregator":
		if value == "" {
			cfg.DefaultAggregator = nil
			typedValue = nil
		} else {
			cfg.DefaultAggregator = &value
			typedValue = value
		}

	case "default_accounting":
		if value == "" {
			cfg.DefaultAccounting = nil
			typedValue = nil
		} else {
			cfg.DefaultAccounting = &value
			typedValue = value
		}

	case "hub_url":
		cfg.HubURL = value
		typedValue = value
	}

	if err := cfg.Save(); err != nil {
		if configSetJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to save config: %v", err)
		}
		return err
	}

	if configSetJSONOutput {
		output.JSON(map[string]interface{}{
			"status": "success",
			"key":    key,
			"value":  typedValue,
		})
	} else {
		output.Success("Set %s = %v", key, typedValue)
	}

	return nil
}

func runConfigShow(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	if configShowJSONOutput {
		// Build aggregators map
		aggregators := make(map[string]map[string]string)
		for alias, agg := range cfg.Aggregators {
			aggregators[alias] = map[string]string{"url": agg.URL}
		}

		// Build accounting services map
		accountingServices := make(map[string]map[string]string)
		for alias, acc := range cfg.AccountingServices {
			accountingServices[alias] = map[string]string{"url": acc.URL}
		}

		data := map[string]interface{}{
			"access_token":        cfg.AccessToken,
			"refresh_token":       cfg.RefreshToken,
			"aggregators":         aggregators,
			"accounting_services": accountingServices,
			"default_aggregator":  cfg.DefaultAggregator,
			"default_accounting":  cfg.DefaultAccounting,
			"timeout":             cfg.Timeout,
			"hub_url":             cfg.HubURL,
		}

		output.JSON(map[string]interface{}{
			"status": "success",
			"config": data,
		})
	} else {
		var values []output.ConfigValue

		// Access token
		var accessToken string
		if cfg.AccessToken != nil {
			accessToken = output.MaskToken(*cfg.AccessToken)
		} else {
			accessToken = output.Dim.Sprint("not set")
		}
		values = append(values, output.ConfigValue{Key: "access_token", Value: accessToken})

		// Refresh token
		var refreshToken string
		if cfg.RefreshToken != nil {
			refreshToken = output.MaskToken(*cfg.RefreshToken)
		} else {
			refreshToken = output.Dim.Sprint("not set")
		}
		values = append(values, output.ConfigValue{Key: "refresh_token", Value: refreshToken})

		// Aggregators
		values = append(values, output.ConfigValue{
			Key:   "aggregators",
			Value: fmt.Sprintf("<%d items>", len(cfg.Aggregators)),
		})

		// Accounting services
		values = append(values, output.ConfigValue{
			Key:   "accounting_services",
			Value: fmt.Sprintf("<%d items>", len(cfg.AccountingServices)),
		})

		// Default aggregator
		var defaultAgg string
		if cfg.DefaultAggregator != nil {
			defaultAgg = *cfg.DefaultAggregator
		} else {
			defaultAgg = output.Dim.Sprint("not set")
		}
		values = append(values, output.ConfigValue{Key: "default_aggregator", Value: defaultAgg})

		// Default accounting
		var defaultAcc string
		if cfg.DefaultAccounting != nil {
			defaultAcc = *cfg.DefaultAccounting
		} else {
			defaultAcc = output.Dim.Sprint("not set")
		}
		values = append(values, output.ConfigValue{Key: "default_accounting", Value: defaultAcc})

		// Timeout
		values = append(values, output.ConfigValue{
			Key:   "timeout",
			Value: fmt.Sprintf("%.1f", cfg.Timeout),
		})

		// Hub URL
		values = append(values, output.ConfigValue{Key: "hub_url", Value: cfg.HubURL})

		output.PrintConfigTable(values)
	}

	return nil
}

func runConfigPath(cmd *cobra.Command, args []string) error {
	if configPathJSONOutput {
		output.JSON(map[string]interface{}{
			"status": "success",
			"path":   config.ConfigFile,
		})
	} else {
		fmt.Println(config.ConfigFile)
	}

	return nil
}
