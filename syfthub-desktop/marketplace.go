// Package main provides marketplace operations for the SyftHub Desktop GUI.
// The marketplace allows users to browse and install pre-built endpoint packages
// from a static JSON manifest hosted at a configurable URL.
package main

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
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

// InstallMarketplacePackage downloads a package zip and extracts it to the endpoints directory.
func (a *App) InstallMarketplacePackage(slug string, downloadURL string) error {
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
	a.setRuntimeState(slug, RuntimeStateInstalling)

	client := nodeops.NewMarketplaceClient(url)
	if err := client.InstallPackage(config.EndpointsPath, slug, downloadURL); err != nil {
		a.clearRuntimeState(slug)
		return err
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Installed marketplace package: %s", slug))

	// If the installed package has setup.yaml, auto-run the setup flow.
	// This mirrors what the CLI does inline after install.
	// RunEndpointSetup will transition the state to "setting_up" → "initializing".
	endpointDir := filepath.Join(config.EndpointsPath, slug)
	if status, err := nodeops.GetSetupStatus(endpointDir); err == nil && status != nil {
		if err := a.RunEndpointSetup(slug, false); err != nil {
			a.clearRuntimeState(slug)
			runtime.LogWarning(a.ctx, fmt.Sprintf("Setup flow failed to start for %s: %v", slug, err))
			runtime.EventsEmit(a.ctx, "setupflow:failed", err.Error())
		} else {
			// State will be managed by RunEndpointSetup goroutine from here
			return nil
		}
	}

	// No setup.yaml or setup failed to start — reload and notify
	if a.core != nil {
		a.core.ReloadEndpoints()
	}
	a.clearRuntimeState(slug)
	a.notifyEndpointsChanged()

	return nil
}

// fromNodeopsMarketplacePackages converts nodeops marketplace packages to desktop types.
func fromNodeopsMarketplacePackages(nPkgs []nodeops.MarketplacePackage) []MarketplacePackage {
	out := make([]MarketplacePackage, len(nPkgs))
	for i, p := range nPkgs {
		out[i] = MarketplacePackage{
			Slug: p.Slug, Name: p.Name, Description: p.Description,
			Type: p.Type, Author: p.Author, Version: p.Version,
			DownloadURL: p.DownloadURL, Tags: p.Tags,
		}
	}
	return out
}
