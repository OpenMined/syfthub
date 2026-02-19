package cmd

import (
	"context"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli-go/internal/config"
	"github.com/OpenMined/syfthub/cli-go/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	lsLimit      int
	lsLongFormat bool
	lsJSONOutput bool
)

var lsCmd = &cobra.Command{
	Use:   "ls [target]",
	Short: "Browse users and endpoints",
	Long: `Browse users and endpoints.

Usage modes:

- syft ls           : List all active users with endpoint counts
- syft ls <user>    : List endpoints for a specific user
- syft ls user/ep   : Show details/README for a specific endpoint`,
	Args: cobra.MaximumNArgs(1),
	RunE: runLs,
}

func init() {
	lsCmd.Flags().IntVarP(&lsLimit, "limit", "n", 50, "Maximum number of results to show")
	lsCmd.Flags().BoolVarP(&lsLongFormat, "long", "l", false, "Use detailed table format")
	lsCmd.Flags().BoolVar(&lsJSONOutput, "json", false, "Output result as JSON")
}

func runLs(cmd *cobra.Command, args []string) error {
	cfg := config.Load()

	// Parse target
	var target string
	if len(args) > 0 {
		target = strings.TrimSuffix(args[0], "/")
	}

	// Create client
	client, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout)*time.Second),
	)
	if err != nil {
		if lsJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to create client: %v", err)
		}
		return err
	}
	defer client.Close()

	// Set tokens if available
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

	if target == "" {
		// Mode 1: List all users
		return listUsers(ctx, client)
	} else if strings.Contains(target, "/") {
		// Mode 3: Show endpoint details
		return showEndpoint(ctx, client, target)
	} else {
		// Mode 2: List user's endpoints
		return listUserEndpoints(ctx, client, target)
	}
}

func listUsers(ctx context.Context, client *syfthub.Client) error {
	owners, err := client.Hub.Owners(ctx, syfthub.WithOwnersLimit(lsLimit))
	if err != nil {
		if lsJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to list: %v", err)
		}
		return err
	}

	// Convert to output format
	ownerInfos := make([]output.OwnerInfo, 0, len(owners))
	for _, owner := range owners {
		ownerInfos = append(ownerInfos, output.OwnerInfo{
			Username:        owner.Username,
			EndpointCount:   owner.EndpointCount,
			ModelCount:      owner.ModelCount,
			DataSourceCount: owner.DataSourceCount,
		})
	}

	if lsJSONOutput {
		result := make([]map[string]interface{}, 0, len(ownerInfos))
		for _, owner := range ownerInfos {
			result = append(result, map[string]interface{}{
				"username":          owner.Username,
				"endpoint_count":    owner.EndpointCount,
				"model_count":       owner.ModelCount,
				"data_source_count": owner.DataSourceCount,
			})
		}
		output.JSON(map[string]interface{}{
			"status": "success",
			"owners": result,
		})
	} else if lsLongFormat {
		output.PrintOwnersTable(ownerInfos)
	} else {
		output.PrintOwnersGrid(ownerInfos)
	}

	return nil
}

func listUserEndpoints(ctx context.Context, client *syfthub.Client, username string) error {
	// Use the efficient ByOwner API (GET /{owner_slug})
	eps, err := client.Hub.ByOwner(ctx, username, syfthub.WithByOwnerLimit(lsLimit))
	if err != nil {
		if lsJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to list: %v", err)
		}
		return err
	}

	// Convert to output format
	endpoints := make([]output.EndpointInfo, 0, len(eps))
	for _, ep := range eps {
		endpoints = append(endpoints, output.EndpointInfo{
			Name:        ep.Name,
			Slug:        ep.Slug,
			Type:        string(ep.Type),
			Version:     ep.Version,
			Stars:       ep.StarsCount,
			Description: ep.Description,
			Owner:       ep.OwnerUsername,
		})
	}

	if lsJSONOutput {
		result := make([]map[string]interface{}, 0, len(endpoints))
		for _, ep := range endpoints {
			result = append(result, map[string]interface{}{
				"name":        ep.Name,
				"type":        ep.Type,
				"version":     ep.Version,
				"stars":       ep.Stars,
				"description": ep.Description,
			})
		}
		output.JSON(map[string]interface{}{
			"status":    "success",
			"endpoints": result,
		})
	} else if lsLongFormat {
		output.PrintEndpointsTable(endpoints, username)
	} else {
		output.PrintEndpointsGrid(endpoints, username)
	}

	return nil
}

func showEndpoint(ctx context.Context, client *syfthub.Client, path string) error {
	ep, err := client.Hub.Get(ctx, path)
	if err != nil {
		if lsJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("%v", err)
		}
		return err
	}

	if lsJSONOutput {
		var createdAt, updatedAt *string
		if !ep.CreatedAt.IsZero() {
			s := ep.CreatedAt.String()
			createdAt = &s
		}
		if !ep.UpdatedAt.IsZero() {
			s := ep.UpdatedAt.String()
			updatedAt = &s
		}

		output.JSON(map[string]interface{}{
			"status": "success",
			"endpoint": map[string]interface{}{
				"owner":       ep.OwnerUsername,
				"name":        ep.Name,
				"type":        string(ep.Type),
				"version":     ep.Version,
				"stars":       ep.StarsCount,
				"description": ep.Description,
				"readme":      ep.Readme,
				"created_at":  createdAt,
				"updated_at":  updatedAt,
			},
		})
	} else {
		output.PrintEndpointDetail(output.EndpointInfo{
			Name:        ep.Name,
			Slug:        ep.Slug,
			Type:        string(ep.Type),
			Version:     ep.Version,
			Stars:       ep.StarsCount,
			Description: ep.Description,
			Owner:       ep.OwnerUsername,
			Readme:      ep.Readme,
		})
	}

	return nil
}
