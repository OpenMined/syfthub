// Package main provides library operations for the SyftHub Desktop GUI.
// The library allows users to browse and install pre-built endpoint packages
// from a static JSON manifest hosted at a configurable URL.
package main

import (
	"fmt"
	neturl "net/url"
	"path/filepath"
	"strings"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// getLibraryURL returns the library manifest URL derived from the configured
// SyftHub URL, with an optional explicit override via settings.MarketplaceURL.
func (a *App) getLibraryURL() string {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.settings != nil && a.settings.MarketplaceURL != "" {
		return a.settings.MarketplaceURL
	}
	if a.settings != nil && a.settings.HubURL != "" {
		return strings.TrimRight(a.settings.HubURL, "/") + "/marketplace/manifest.json"
	}
	return ""
}

// GetLibraryPackages fetches and returns available packages from the library manifest.
func (a *App) GetLibraryPackages() ([]LibraryPackage, error) {
	url := a.getLibraryURL()
	if url == "" {
		return nil, fmt.Errorf("library unavailable: no SyftHub URL configured")
	}

	client := a.getLibraryClient(url)
	nPkgs, err := client.FetchPackages()
	if err != nil {
		runtime.LogError(a.ctx, fmt.Sprintf("Failed to fetch library manifest: %v", err))
		return nil, err
	}

	pkgs := fromNodeopsLibraryPackages(nPkgs)
	runtime.LogInfo(a.ctx, fmt.Sprintf("Loaded %d packages from library", len(pkgs)))
	return pkgs, nil
}

// InstallLibraryPackage downloads a package zip, extracts it to the endpoints directory,
// and writes any user-supplied config values to the endpoint's .env file.
// configValues maps env var keys to user-provided values (empty values are skipped).
func (a *App) InstallLibraryPackage(slug string, downloadURL string, configValues map[string]string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	url := a.getLibraryURL()
	if url == "" {
		return fmt.Errorf("library unavailable: no SyftHub URL configured")
	}

	// Validate that downloadURL points to the same origin as the library
	// to prevent SSRF via attacker-controlled URLs from the frontend.
	parsedLibrary, err := neturl.Parse(url)
	if err != nil {
		return fmt.Errorf("invalid library URL: %w", err)
	}
	parsedDownload, err := neturl.Parse(downloadURL)
	if err != nil {
		return fmt.Errorf("invalid download URL: %w", err)
	}
	if parsedDownload.Scheme != parsedLibrary.Scheme || parsedDownload.Host != parsedLibrary.Host {
		return fmt.Errorf("download URL origin does not match library origin")
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Downloading library package: %s", slug))
	a.setRuntimeState(slug, RuntimeStateInstalling)

	client := a.getLibraryClient(url)
	if err := client.InstallPackage(config.EndpointsPath, slug, downloadURL); err != nil {
		a.clearRuntimeState(slug)
		return err
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Installed library package: %s", slug))

	// Merge user-supplied config values into the endpoint's .env file,
	// preserving any defaults the package zip already shipped.
	if len(configValues) > 0 {
		endpointEnvPath := filepath.Join(config.EndpointsPath, slug, ".env")
		if err := nodeops.MergeEnvFile(endpointEnvPath, configValues, true); err != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("Failed to write .env for %s: %v", slug, err))
		}
	}

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

// Compile-time check: PackageConfigField must stay in sync with nodeops.PackageConfigField.
// If a field is added/removed/reordered in nodeops, this line will fail to compile.
var _ = func() { _ = PackageConfigField(nodeops.PackageConfigField{}) }

// fromNodeopsLibraryPackages converts nodeops marketplace packages to desktop types.
func fromNodeopsLibraryPackages(nPkgs []nodeops.MarketplacePackage) []LibraryPackage {
	out := make([]LibraryPackage, len(nPkgs))
	for i, p := range nPkgs {
		cfg := make([]PackageConfigField, len(p.Config))
		for j, f := range p.Config {
			cfg[j] = PackageConfigField(f)
		}
		out[i] = LibraryPackage{
			Slug: p.Slug, Name: p.Name, Description: p.Description,
			Type: p.Type, Author: p.Author, Version: p.Version,
			DownloadURL: p.DownloadURL, Tags: p.Tags, Config: cfg,
		}
	}
	return out
}
