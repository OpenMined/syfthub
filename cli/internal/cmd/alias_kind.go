package cmd

import (
	"sort"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

// aliasKind captures everything that differs between the aggregator and
// accounting-service alias CRUD commands. The command handlers are shared
// and parameterized via this struct.
type aliasKind struct {
	name       string // "aggregator" / "accounting service" — for user-facing messages
	jsonKey    string // "aggregators" / "accounting_services" — for JSON envelope field
	tableTitle string // "Aggregator" / "Accounting" — passed to output.PrintAliasesTable
	get        func(cfg *config.Config) map[string]string
	set        func(cfg *config.Config, alias, url string)
	del        func(cfg *config.Config, alias string)
	getDefault func(cfg *config.Config) string
	setDefault func(cfg *config.Config, alias string)
}

var aggregatorKind = aliasKind{
	name:       "aggregator",
	jsonKey:    "aggregators",
	tableTitle: "Aggregator",
	get: func(cfg *config.Config) map[string]string {
		out := make(map[string]string, len(cfg.Aggregators))
		for k, v := range cfg.Aggregators {
			out[k] = v.URL
		}
		return out
	},
	set: func(cfg *config.Config, alias, url string) {
		cfg.Aggregators[alias] = config.AggregatorConfig{URL: url}
	},
	del: func(cfg *config.Config, alias string) {
		delete(cfg.Aggregators, alias)
	},
	getDefault: func(cfg *config.Config) string { return cfg.DefaultAggregator },
	setDefault: func(cfg *config.Config, alias string) { cfg.DefaultAggregator = alias },
}

var accountingKind = aliasKind{
	name:       "accounting service",
	jsonKey:    "accounting_services",
	tableTitle: "Accounting",
	get: func(cfg *config.Config) map[string]string {
		out := make(map[string]string, len(cfg.AccountingServices))
		for k, v := range cfg.AccountingServices {
			out[k] = v.URL
		}
		return out
	},
	set: func(cfg *config.Config, alias, url string) {
		cfg.AccountingServices[alias] = config.AccountingConfig{URL: url}
	},
	del: func(cfg *config.Config, alias string) {
		delete(cfg.AccountingServices, alias)
	},
	getDefault: func(cfg *config.Config) string { return cfg.DefaultAccounting },
	setDefault: func(cfg *config.Config, alias string) { cfg.DefaultAccounting = alias },
}

// capitalize returns s with its first ASCII letter upper-cased.
func capitalize(s string) string {
	if s == "" {
		return s
	}
	b := []byte(s)
	if b[0] >= 'a' && b[0] <= 'z' {
		b[0] -= 'a' - 'A'
	}
	return string(b)
}

func runAddAlias(k aliasKind, alias, url string, setDefault, jsonMode bool) error {
	cfg := config.Load()

	if _, exists := k.get(cfg)[alias]; exists {
		if jsonMode {
			output.JSON(map[string]any{
				"status":  output.StatusError,
				"message": capitalize(k.name) + " '" + alias + "' already exists",
			})
		} else {
			output.Error("%s '%s' already exists. Use 'syft update %s' to modify it.", capitalize(k.name), alias, firstWord(k.name))
		}
		return nil
	}

	k.set(cfg, alias, url)

	if setDefault {
		k.setDefault(cfg, alias)
	}

	if err := cfg.Save(); err != nil {
		return output.ReplyError(jsonMode, "Failed to save config: %v", err)
	}

	msg := "Added " + k.name + " '" + alias + "' -> " + url
	if setDefault {
		msg += " (default)"
	}
	output.ReplySuccess(jsonMode, map[string]any{
		"alias":      alias,
		"url":        url,
		"is_default": setDefault,
	}, "%s", msg)

	return nil
}

func runUpdateAlias(k aliasKind, alias, newURL string, setDefault, jsonMode bool) error {
	cfg := config.Load()

	if _, exists := k.get(cfg)[alias]; !exists {
		if jsonMode {
			output.JSON(map[string]any{
				"status":  output.StatusError,
				"message": capitalize(k.name) + " '" + alias + "' not found",
			})
		} else {
			output.Error("%s '%s' not found.", capitalize(k.name), alias)
		}
		return nil
	}

	if newURL == "" && !setDefault {
		if jsonMode {
			output.JSON(map[string]any{
				"status":  output.StatusError,
				"message": "Nothing to update",
			})
		} else {
			output.Warning("Nothing to update. Specify --url or --default.")
		}
		return nil
	}

	if newURL != "" {
		k.set(cfg, alias, newURL)
	}

	if setDefault {
		k.setDefault(cfg, alias)
	}

	if err := cfg.Save(); err != nil {
		return output.ReplyError(jsonMode, "Failed to save config: %v", err)
	}

	isDefault := k.getDefault(cfg) == alias

	output.ReplySuccess(jsonMode, map[string]any{
		"alias":      alias,
		"url":        k.get(cfg)[alias],
		"is_default": isDefault,
	}, "Updated %s '%s'", k.name, alias)

	return nil
}

func runListAlias(k aliasKind, jsonMode bool) error {
	cfg := config.Load()
	entries := k.get(cfg)
	def := k.getDefault(cfg)

	if jsonMode {
		result := make(map[string]any)
		for alias, url := range entries {
			result[alias] = map[string]any{
				"url":        url,
				"is_default": def == alias,
			}
		}
		output.JSON(map[string]any{
			"status":  output.StatusSuccess,
			k.jsonKey: result,
		})
		return nil
	}

	aliases := make([]output.AliasInfo, 0, len(entries))
	for alias, url := range entries {
		aliases = append(aliases, output.AliasInfo{
			Name:      alias,
			URL:       url,
			IsDefault: def == alias,
		})
	}
	sort.Slice(aliases, func(i, j int) bool {
		return aliases[i].Name < aliases[j].Name
	})
	output.PrintAliasesTable(aliases, k.tableTitle)
	return nil
}

func runRemoveAlias(k aliasKind, alias string, jsonMode bool) error {
	cfg := config.Load()

	if _, exists := k.get(cfg)[alias]; !exists {
		if jsonMode {
			output.JSON(map[string]any{
				"status":  output.StatusError,
				"message": capitalize(k.name) + " '" + alias + "' not found",
			})
		} else {
			output.Error("%s '%s' not found.", capitalize(k.name), alias)
		}
		return nil
	}

	k.del(cfg, alias)

	// Clear default if it was this alias
	if k.getDefault(cfg) == alias {
		k.setDefault(cfg, "")
	}

	if err := cfg.Save(); err != nil {
		return output.ReplyError(jsonMode, "Failed to save config: %v", err)
	}

	output.ReplySuccess(jsonMode, map[string]any{
		"alias":   alias,
		"message": "Removed",
	}, "Removed %s '%s'", k.name, alias)

	return nil
}

// firstWord returns the first space-separated word of s.
// Used to build command hints like "syft update aggregator" from "aggregator service".
func firstWord(s string) string {
	for i := 0; i < len(s); i++ {
		if s[i] == ' ' {
			return s[:i]
		}
	}
	return s
}
