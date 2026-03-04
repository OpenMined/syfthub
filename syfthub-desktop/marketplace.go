// Package main provides marketplace operations for the SyftHub Desktop GUI.
// The marketplace allows users to browse and install pre-built endpoint packages
// from a static JSON manifest hosted at a configurable URL.
package main

import (
	"fmt"
	"strings"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/OpenMined/syfthub/pkg/nodeops"
)

// getMarketplaceURL returns the marketplace manifest URL derived from the configured
// SyftHub URL, with an optional explicit override via settings.MarketplaceURL.
func (a *App) getMarketplaceURL() string {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.settings != nil && a.settings.MarketplaceURL != "" {
		return a.settings.MarketplaceURL
	}
	if a.settings != nil && a.settings.SyftHubURL != "" {
		return strings.TrimRight(a.settings.SyftHubURL, "/") + "/marketplace/manifest.json"
	}
	return ""
}

// GetMarketplacePackages fetches and returns available packages from the marketplace manifest.
func (a *App) GetMarketplacePackages() ([]MarketplacePackage, error) {
	url := a.getMarketplaceURL()
	if url == "" {
		return nil, fmt.Errorf("marketplace unavailable: no SyftHub URL configured")
	}

	client := nodeops.NewMarketplaceClient(url)
	nPkgs, err := client.FetchPackages()
	if err != nil {
		runtime.LogError(a.ctx, fmt.Sprintf("Failed to fetch marketplace manifest: %v", err))
		return nil, err
	}

	pkgs := fromNodeopsMarketplacePackages(nPkgs)
	runtime.LogInfo(a.ctx, fmt.Sprintf("Loaded %d packages from marketplace", len(pkgs)))
	return pkgs, nil
}

// InstallMarketplacePackage downloads a package zip, extracts it to the endpoints
// directory, and writes a .env file with the provided configuration values.
func (a *App) InstallMarketplacePackage(slug string, downloadURL string, configValues []EnvVar) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	url := a.getMarketplaceURL()
	if url == "" {
		return fmt.Errorf("marketplace unavailable: no SyftHub URL configured")
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Downloading marketplace package: %s", slug))

	client := nodeops.NewMarketplaceClient(url)
	if err := client.InstallPackage(config.EndpointsPath, slug, downloadURL, toNodeopsEnvVars(configValues)); err != nil {
		return err
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Installed marketplace package: %s", slug))
	return nil
}

// fromNodeopsMarketplacePackages converts nodeops marketplace packages to desktop types.
func fromNodeopsMarketplacePackages(nPkgs []nodeops.MarketplacePackage) []MarketplacePackage {
	out := make([]MarketplacePackage, len(nPkgs))
	for i, p := range nPkgs {
		var configFields []PackageConfigField
		for _, f := range p.ConfigFields {
			configFields = append(configFields, PackageConfigField{
				Key: f.Key, Label: f.Label, Description: f.Description,
				Required: f.Required, Secret: f.Secret, Default: f.Default,
			})
		}
		out[i] = MarketplacePackage{
			Slug: p.Slug, Name: p.Name, Description: p.Description,
			Type: p.Type, Author: p.Author, Version: p.Version,
			DownloadURL: p.DownloadURL, Tags: p.Tags, ConfigFields: configFields,
		}
	}
	return out
}
