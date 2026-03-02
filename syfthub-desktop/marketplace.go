// Package main provides marketplace operations for the SyftHub Desktop GUI.
// The marketplace allows users to browse and install pre-built endpoint packages
// from a static JSON manifest hosted at a configurable URL.
package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

const defaultMarketplaceURL = "https://raw.githubusercontent.com/openmined/syfthub-marketplace/main/manifest.json"

// getMarketplaceURL returns the configured marketplace manifest URL,
// falling back to the default if not set.
func (a *App) getMarketplaceURL() string {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.settings != nil && a.settings.MarketplaceURL != "" {
		return a.settings.MarketplaceURL
	}
	return defaultMarketplaceURL
}

// GetMarketplacePackages fetches and returns available packages from the marketplace manifest.
func (a *App) GetMarketplacePackages() ([]MarketplacePackage, error) {
	url := a.getMarketplaceURL()

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		runtime.LogError(a.ctx, fmt.Sprintf("Failed to fetch marketplace manifest: %v", err))
		return nil, fmt.Errorf("failed to fetch marketplace: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		runtime.LogError(a.ctx, fmt.Sprintf("Marketplace manifest returned status %d", resp.StatusCode))
		return nil, fmt.Errorf("marketplace returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read marketplace response: %v", err)
	}

	var manifest MarketplaceManifest
	if err := json.Unmarshal(body, &manifest); err != nil {
		return nil, fmt.Errorf("failed to parse marketplace manifest: %v", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Loaded %d packages from marketplace", len(manifest.Packages)))
	return manifest.Packages, nil
}

// InstallMarketplacePackage downloads a package zip, extracts it to the endpoints
// directory, and writes a .env file with the provided configuration values.
func (a *App) InstallMarketplacePackage(slug string, downloadURL string, configValues []EnvVar) error {
	// Validate slug
	if slug == "" {
		return fmt.Errorf("package slug is required")
	}
	if strings.Contains(slug, "..") || strings.Contains(slug, "/") || strings.Contains(slug, "\\") {
		return fmt.Errorf("invalid package slug")
	}

	// Download the zip (outside lock — can be slow)
	runtime.LogInfo(a.ctx, fmt.Sprintf("Downloading marketplace package: %s", slug))
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Get(downloadURL)
	if err != nil {
		return fmt.Errorf("failed to download package: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("package download returned status %d", resp.StatusCode)
	}

	zipData, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read package data: %v", err)
	}

	// Lock for filesystem operations
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.config == nil {
		return fmt.Errorf("app not configured")
	}

	targetDir := filepath.Join(a.config.EndpointsPath, slug)

	// Check if already installed
	if _, err := os.Stat(targetDir); err == nil {
		return fmt.Errorf("package %q is already installed", slug)
	}

	// Create target directory
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		return fmt.Errorf("failed to create package directory: %v", err)
	}

	// Cleanup on failure
	success := false
	defer func() {
		if !success {
			os.RemoveAll(targetDir)
		}
	}()

	// Extract zip
	zipReader, err := zip.NewReader(bytes.NewReader(zipData), int64(len(zipData)))
	if err != nil {
		return fmt.Errorf("failed to read zip archive: %v", err)
	}

	for _, entry := range zipReader.File {
		if entry.FileInfo().IsDir() {
			continue
		}

		// Determine the relative path within the package.
		// Zips may have a top-level directory wrapper (e.g. "slug/runner.py")
		// or be flat (e.g. "runner.py"). We strip the first path component
		// if all entries share a common prefix directory.
		entryName := filepath.ToSlash(entry.Name)

		// Zip-slip protection: reject entries with path traversal
		if strings.Contains(entryName, "..") {
			continue
		}

		// Strip the common top-level directory if present
		relPath := stripTopLevelDir(entryName, zipReader.File)

		destPath := filepath.Join(targetDir, relPath)

		// Verify the destination is still under targetDir (zip-slip check)
		cleanDest := filepath.Clean(destPath)
		if !strings.HasPrefix(cleanDest, filepath.Clean(targetDir)+string(os.PathSeparator)) && cleanDest != filepath.Clean(targetDir) {
			continue
		}

		// Create parent directories
		if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
			return fmt.Errorf("failed to create directory for %s: %v", relPath, err)
		}

		// Extract file
		rc, err := entry.Open()
		if err != nil {
			return fmt.Errorf("failed to open zip entry %s: %v", entry.Name, err)
		}

		data, err := io.ReadAll(rc)
		rc.Close()
		if err != nil {
			return fmt.Errorf("failed to read zip entry %s: %v", entry.Name, err)
		}

		if err := os.WriteFile(destPath, data, 0644); err != nil {
			return fmt.Errorf("failed to write %s: %v", relPath, err)
		}
	}

	// Write .env with user-provided configuration
	if len(configValues) > 0 {
		envPath := filepath.Join(targetDir, ".env")
		if err := a.writeEnvFile(envPath, configValues); err != nil {
			return fmt.Errorf("failed to write configuration: %v", err)
		}
	}

	success = true
	runtime.LogInfo(a.ctx, fmt.Sprintf("Installed marketplace package: %s", slug))
	return nil
}

// stripTopLevelDir determines if all zip entries share a common top-level directory
// and returns the entry path with that prefix stripped. If entries are flat (no
// common prefix), returns the original path.
func stripTopLevelDir(entryName string, files []*zip.File) string {
	parts := strings.SplitN(entryName, "/", 2)
	if len(parts) < 2 {
		// File is at the root level — no stripping needed
		return entryName
	}

	prefix := parts[0] + "/"

	// Check if ALL non-directory entries share this prefix
	for _, f := range files {
		if f.FileInfo().IsDir() {
			continue
		}
		name := filepath.ToSlash(f.Name)
		if !strings.HasPrefix(name, prefix) {
			// Not all entries share the prefix — don't strip
			return entryName
		}
	}

	// All entries share the prefix — strip it
	return strings.TrimPrefix(entryName, prefix)
}
