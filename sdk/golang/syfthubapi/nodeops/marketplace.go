package nodeops

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
)

// MarketplaceClient provides marketplace HTTP operations.
type MarketplaceClient struct {
	ManifestURL string
	HTTPClient  *http.Client
}

// NewMarketplaceClient creates a new MarketplaceClient with a 15-second default timeout.
func NewMarketplaceClient(manifestURL string) *MarketplaceClient {
	return &MarketplaceClient{
		ManifestURL: manifestURL,
		HTTPClient:  &http.Client{Timeout: 15 * time.Second},
	}
}

// FetchPackages fetches and returns available packages from the marketplace manifest.
func (c *MarketplaceClient) FetchPackages() ([]MarketplacePackage, error) {
	if c.ManifestURL == "" {
		return nil, fmt.Errorf("marketplace URL is not configured")
	}

	resp, err := c.HTTPClient.Get(c.ManifestURL)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch marketplace: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("marketplace returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read marketplace response: %w", err)
	}

	var manifest MarketplaceManifest
	if err := json.Unmarshal(body, &manifest); err != nil {
		return nil, fmt.Errorf("failed to parse marketplace manifest: %w", err)
	}

	return manifest.Packages, nil
}

// InstallPackage downloads a package zip and extracts it to endpointsPath/slug.
func (c *MarketplaceClient) InstallPackage(endpointsPath, slug, downloadURL string) error {
	if slug == "" {
		return fmt.Errorf("package slug is required")
	}
	if strings.Contains(slug, "..") || strings.Contains(slug, "/") || strings.Contains(slug, "\\") {
		return fmt.Errorf("invalid package slug")
	}

	// Download the zip
	downloadClient := &http.Client{Timeout: 60 * time.Second}
	resp, err := downloadClient.Get(downloadURL)
	if err != nil {
		return fmt.Errorf("failed to download package: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("package download returned status %d", resp.StatusCode)
	}

	const maxDownloadSize = 100 << 20 // 100 MB
	zipData, err := io.ReadAll(io.LimitReader(resp.Body, maxDownloadSize+1))
	if err != nil {
		return fmt.Errorf("failed to read package data: %w", err)
	}
	if len(zipData) > maxDownloadSize {
		return fmt.Errorf("package exceeds maximum size of %d MB", maxDownloadSize>>20)
	}

	targetDir := filepath.Join(endpointsPath, slug)

	if _, err := os.Stat(targetDir); err == nil {
		return fmt.Errorf("package %q is already installed", slug)
	}

	if err := os.MkdirAll(targetDir, 0755); err != nil {
		return fmt.Errorf("failed to create package directory: %w", err)
	}

	success := false
	defer func() {
		if !success {
			os.RemoveAll(targetDir)
		}
	}()

	zipReader, err := zip.NewReader(bytes.NewReader(zipData), int64(len(zipData)))
	if err != nil {
		return fmt.Errorf("failed to read zip archive: %w", err)
	}

	// Pre-compute whether all entries share a common top-level directory
	topLevelPrefix := commonTopLevelDir(zipReader.File)

	for _, entry := range zipReader.File {
		if entry.FileInfo().IsDir() {
			continue
		}

		entryName := filepath.ToSlash(entry.Name)

		// Zip-slip protection
		if strings.Contains(entryName, "..") {
			continue
		}

		relPath := strings.TrimPrefix(entryName, topLevelPrefix)
		destPath := filepath.Join(targetDir, relPath)

		cleanDest := filepath.Clean(destPath)
		if !strings.HasPrefix(cleanDest, filepath.Clean(targetDir)+string(os.PathSeparator)) && cleanDest != filepath.Clean(targetDir) {
			continue
		}

		if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
			return fmt.Errorf("failed to create directory for %s: %w", relPath, err)
		}

		rc, err := entry.Open()
		if err != nil {
			return fmt.Errorf("failed to open zip entry %s: %w", entry.Name, err)
		}

		outFile, err := os.OpenFile(destPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
		if err != nil {
			rc.Close()
			return fmt.Errorf("failed to create %s: %w", relPath, err)
		}
		_, err = io.Copy(outFile, rc)
		outFile.Close()
		rc.Close()
		if err != nil {
			return fmt.Errorf("failed to write %s: %w", relPath, err)
		}
	}

	success = true
	return nil
}

// commonTopLevelDir returns the common top-level directory prefix shared by all
// file entries in the zip (e.g. "pkg-v1/"). Returns "" if entries do not share
// a common prefix.
func commonTopLevelDir(files []*zip.File) string {
	var prefix string
	for _, f := range files {
		if f.FileInfo().IsDir() {
			continue
		}
		name := filepath.ToSlash(f.Name)
		parts := strings.SplitN(name, "/", 2)
		if len(parts) < 2 {
			return "" // file at root level — no common prefix
		}
		candidate := parts[0] + "/"
		if prefix == "" {
			prefix = candidate
		} else if prefix != candidate {
			return "" // mismatch
		}
	}
	return prefix
}
