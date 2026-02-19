// Package completion provides dynamic shell completion for SyftHub CLI.
package completion

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/config"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

// Cache configuration.
const (
	CacheTTL = 5 * time.Minute
)

// CachedEndpoint represents a cached endpoint for completion.
type CachedEndpoint struct {
	Owner       string `json:"owner"`
	Name        string `json:"name"`
	Type        string `json:"type"`
	Description string `json:"description"`
}

// CompletionCache represents the cached completion data.
type CompletionCache struct {
	Endpoints []CachedEndpoint `json:"endpoints"`
	Timestamp int64            `json:"timestamp"`
}

// getCacheFile returns the path to the completion cache file.
func getCacheFile() string {
	return filepath.Join(os.Getenv("HOME"), ".syfthub", ".completion_cache.json")
}

// getCachedEndpoints returns cached endpoints if valid.
func getCachedEndpoints() []CachedEndpoint {
	cacheFile := getCacheFile()
	data, err := os.ReadFile(cacheFile)
	if err != nil {
		return nil
	}

	var cache CompletionCache
	if err := json.Unmarshal(data, &cache); err != nil {
		return nil
	}

	// Check if cache is still valid
	if time.Now().Unix()-cache.Timestamp > int64(CacheTTL.Seconds()) {
		return nil
	}

	return cache.Endpoints
}

// fetchAndCacheEndpoints fetches endpoints from API and caches them.
func fetchAndCacheEndpoints() []CachedEndpoint {
	cfg := config.Load()

	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(10*time.Second),
	)
	if err != nil {
		return nil
	}
	defer client.Close()

	if cfg.HasTokens() {
		refreshToken := ""
		if cfg.RefreshToken != nil {
			refreshToken = *cfg.RefreshToken
		}
		client.SetTokens(&syfthub.AuthTokens{
			AccessToken:  *cfg.AccessToken,
			RefreshToken: refreshToken,
		})
	}

	ctx := context.Background()
	var endpoints []CachedEndpoint

	iter := client.Hub.Browse(ctx, syfthub.WithPageSize(100))
	count := 0
	for iter.Next(ctx) {
		ep := iter.Value()
		endpoints = append(endpoints, CachedEndpoint{
			Owner:       ep.OwnerUsername,
			Name:        ep.Slug,
			Type:        string(ep.Type),
			Description: ep.Description,
		})
		count++
		if count >= 500 { // Limit for completion performance
			break
		}
	}

	// Cache the results
	cacheFile := getCacheFile()
	cacheDir := filepath.Dir(cacheFile)
	if err := os.MkdirAll(cacheDir, 0755); err == nil {
		cache := CompletionCache{
			Endpoints: endpoints,
			Timestamp: time.Now().Unix(),
		}
		if data, err := json.Marshal(cache); err == nil {
			_ = os.WriteFile(cacheFile, data, 0600)
		}
	}

	return endpoints
}

// getEndpoints returns endpoints, using cache if available.
func getEndpoints() []CachedEndpoint {
	if cached := getCachedEndpoints(); cached != nil {
		return cached
	}
	return fetchAndCacheEndpoints()
}

// CompleteLsTarget provides completion for the ls command target.
// - If incomplete doesn't contain "/" -> complete usernames
// - If incomplete contains "/" -> complete endpoints for that user
func CompleteLsTarget(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	if len(args) > 0 {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}

	endpoints := getEndpoints()
	if endpoints == nil {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}

	var completions []string

	if strings.Contains(toComplete, "/") {
		// User is typing an endpoint path like "alice/my-"
		parts := strings.SplitN(toComplete, "/", 2)
		userPrefix := strings.ToLower(parts[0])
		endpointPrefix := ""
		if len(parts) > 1 {
			endpointPrefix = strings.ToLower(parts[1])
		}

		for _, ep := range endpoints {
			if strings.ToLower(ep.Owner) == userPrefix {
				if strings.HasPrefix(strings.ToLower(ep.Name), endpointPrefix) {
					fullPath := ep.Owner + "/" + ep.Name
					desc := ep.Type
					if ep.Description != "" {
						if len(ep.Description) > 40 {
							desc = ep.Type + ": " + ep.Description[:40] + "..."
						} else {
							desc = ep.Type + ": " + ep.Description
						}
					}
					completions = append(completions, fullPath+"\t"+desc)
				}
			}
		}
	} else {
		// User is typing a username
		seenUsers := make(map[string]int)
		for _, ep := range endpoints {
			if strings.HasPrefix(strings.ToLower(ep.Owner), strings.ToLower(toComplete)) {
				seenUsers[ep.Owner]++
			}
		}

		for user, count := range seenUsers {
			desc := "1 endpoint"
			if count > 1 {
				desc = fmt.Sprintf("%d endpoints", count)
			}
			completions = append(completions, user+"/\t"+desc)
		}
	}

	return completions, cobra.ShellCompDirectiveNoFileComp | cobra.ShellCompDirectiveNoSpace
}

// CompleteModelEndpoint provides completion for model endpoint paths.
func CompleteModelEndpoint(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	if len(args) > 0 {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}

	endpoints := getEndpoints()
	if endpoints == nil {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}

	var completions []string
	for _, ep := range endpoints {
		if ep.Type != "model" {
			continue
		}

		fullPath := ep.Owner + "/" + ep.Name
		if strings.HasPrefix(strings.ToLower(fullPath), strings.ToLower(toComplete)) {
			desc := "model"
			if ep.Description != "" {
				if len(ep.Description) > 50 {
					desc = ep.Description[:50] + "..."
				} else {
					desc = ep.Description
				}
			}
			completions = append(completions, fullPath+"\t"+desc)
		}
	}

	return completions, cobra.ShellCompDirectiveNoFileComp
}

// CompleteDataSource provides completion for data source endpoint paths.
func CompleteDataSource(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	if len(args) > 0 {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}

	endpoints := getEndpoints()
	if endpoints == nil {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}

	var completions []string
	for _, ep := range endpoints {
		if ep.Type != "data_source" && ep.Type != "model_data_source" {
			continue
		}

		fullPath := ep.Owner + "/" + ep.Name
		if strings.HasPrefix(strings.ToLower(fullPath), strings.ToLower(toComplete)) {
			desc := ep.Type
			if ep.Description != "" {
				if len(ep.Description) > 50 {
					desc = ep.Description[:50] + "..."
				} else {
					desc = ep.Description
				}
			}
			completions = append(completions, fullPath+"\t"+desc)
		}
	}

	return completions, cobra.ShellCompDirectiveNoFileComp
}

// CompleteAggregatorAlias provides completion for aggregator aliases.
func CompleteAggregatorAlias(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	cfg := config.Load()
	var completions []string

	for alias, agg := range cfg.Aggregators {
		if strings.HasPrefix(strings.ToLower(alias), strings.ToLower(toComplete)) {
			completions = append(completions, alias+"\t"+agg.URL)
		}
	}

	return completions, cobra.ShellCompDirectiveNoFileComp
}

// CompleteAccountingAlias provides completion for accounting service aliases.
func CompleteAccountingAlias(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	cfg := config.Load()
	var completions []string

	for alias, acc := range cfg.AccountingServices {
		if strings.HasPrefix(strings.ToLower(alias), strings.ToLower(toComplete)) {
			completions = append(completions, alias+"\t"+acc.URL)
		}
	}

	return completions, cobra.ShellCompDirectiveNoFileComp
}

// CompleteConfigKey provides completion for configuration keys.
func CompleteConfigKey(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	if len(args) > 0 {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}

	keys := map[string]string{
		"default_aggregator": "Default aggregator alias",
		"default_accounting": "Default accounting service alias",
		"timeout":            "Request timeout in seconds",
		"hub_url":            "SyftHub API URL",
	}

	var completions []string
	for key, desc := range keys {
		if strings.HasPrefix(strings.ToLower(key), strings.ToLower(toComplete)) {
			completions = append(completions, key+"\t"+desc)
		}
	}

	return completions, cobra.ShellCompDirectiveNoFileComp
}
