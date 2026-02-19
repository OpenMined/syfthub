// Package update provides self-update functionality for the CLI.
package update

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/version"
)

const (
	// GitHubRepo is the repository for releases.
	GitHubRepo = "OpenMined/syfthub"
	// GitHubAPIURL is the releases API endpoint.
	GitHubAPIURL = "https://api.github.com/repos/" + GitHubRepo + "/releases"
	// CheckIntervalHours is how often to check for updates.
	CheckIntervalHours = 24
)

// VersionInfo contains information about a release.
type VersionInfo struct {
	Version     string
	DownloadURL string
	ReleaseURL  string
	PublishedAt string
}

// ParseVersion parses a version string into comparable integers.
func ParseVersion(v string) []int {
	v = strings.TrimPrefix(v, "v")
	parts := strings.Split(strings.Split(v, "-")[0], ".")

	result := make([]int, len(parts))
	for i, p := range parts {
		n, _ := strconv.Atoi(p)
		result[i] = n
	}
	return result
}

// IsNewerVersion checks if latest is newer than current.
func IsNewerVersion(latest, current string) bool {
	latestParts := ParseVersion(latest)
	currentParts := ParseVersion(current)

	for i := 0; i < len(latestParts) && i < len(currentParts); i++ {
		if latestParts[i] > currentParts[i] {
			return true
		}
		if latestParts[i] < currentParts[i] {
			return false
		}
	}
	return len(latestParts) > len(currentParts)
}

// GetPlatformBinaryName returns the binary name for the current platform.
func GetPlatformBinaryName() string {
	osName := runtime.GOOS
	arch := runtime.GOARCH

	// Map architectures
	archMap := map[string]string{
		"amd64": "x64",
		"arm64": "arm64",
	}
	if mapped, ok := archMap[arch]; ok {
		arch = mapped
	}

	// macOS: only arm64 binary is available
	if osName == "darwin" {
		arch = "arm64"
	}

	if osName == "windows" {
		return fmt.Sprintf("syft-%s-%s.exe", osName, arch)
	}
	return fmt.Sprintf("syft-%s-%s", osName, arch)
}

// GetLatestRelease fetches the latest CLI release from GitHub.
func GetLatestRelease() (*VersionInfo, error) {
	client := &http.Client{Timeout: 10 * time.Second}

	resp, err := client.Get(GitHubAPIURL)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GitHub API returned status %d", resp.StatusCode)
	}

	var releases []struct {
		TagName     string `json:"tag_name"`
		HTMLURL     string `json:"html_url"`
		PublishedAt string `json:"published_at"`
		Assets      []struct {
			Name               string `json:"name"`
			BrowserDownloadURL string `json:"browser_download_url"`
		} `json:"assets"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&releases); err != nil {
		return nil, err
	}

	binaryName := GetPlatformBinaryName()

	// Find the latest CLI release (tag starts with "cli/v")
	for _, release := range releases {
		if strings.HasPrefix(release.TagName, "cli/v") {
			version := strings.TrimPrefix(release.TagName, "cli/v")

			for _, asset := range release.Assets {
				if asset.Name == binaryName {
					return &VersionInfo{
						Version:     version,
						DownloadURL: asset.BrowserDownloadURL,
						ReleaseURL:  release.HTMLURL,
						PublishedAt: release.PublishedAt,
					}, nil
				}
			}
		}
	}

	return nil, nil
}

// UpdateCache represents cached update check data.
type UpdateCache struct {
	LastCheck     string `json:"last_check"`
	LatestVersion string `json:"latest_version"`
	DownloadURL   string `json:"download_url"`
	ReleaseURL    string `json:"release_url"`
	PublishedAt   string `json:"published_at"`
}

// LoadUpdateCache loads cached update check data.
func LoadUpdateCache() *UpdateCache {
	data, err := os.ReadFile(config.UpdateCheckFile)
	if err != nil {
		return nil
	}

	var cache UpdateCache
	if err := json.Unmarshal(data, &cache); err != nil {
		return nil
	}

	return &cache
}

// SaveUpdateCache saves update check data to cache.
func SaveUpdateCache(cache *UpdateCache) error {
	if err := config.EnsureConfigDir(); err != nil {
		return err
	}

	data, err := json.Marshal(cache)
	if err != nil {
		return err
	}

	return os.WriteFile(config.UpdateCheckFile, data, 0600)
}

// ShouldCheckForUpdates returns true if enough time has passed since last check.
func ShouldCheckForUpdates() bool {
	cache := LoadUpdateCache()
	if cache == nil || cache.LastCheck == "" {
		return true
	}

	lastCheck, err := time.Parse(time.RFC3339, cache.LastCheck)
	if err != nil {
		return true
	}

	return time.Since(lastCheck) > time.Duration(CheckIntervalHours)*time.Hour
}

// CheckForUpdates checks if a newer version is available.
func CheckForUpdates(force bool) (*VersionInfo, error) {
	cache := LoadUpdateCache()

	// Use cached result if recent enough and not forcing
	if !force && !ShouldCheckForUpdates() {
		if cache != nil && cache.LatestVersion != "" && IsNewerVersion(cache.LatestVersion, version.Version) {
			return &VersionInfo{
				Version:     cache.LatestVersion,
				DownloadURL: cache.DownloadURL,
				ReleaseURL:  cache.ReleaseURL,
				PublishedAt: cache.PublishedAt,
			}, nil
		}
		return nil, nil
	}

	// Fetch latest release
	latest, err := GetLatestRelease()
	if err != nil {
		return nil, err
	}

	// Update cache
	newCache := &UpdateCache{
		LastCheck: time.Now().UTC().Format(time.RFC3339),
	}
	if latest != nil {
		newCache.LatestVersion = latest.Version
		newCache.DownloadURL = latest.DownloadURL
		newCache.ReleaseURL = latest.ReleaseURL
		newCache.PublishedAt = latest.PublishedAt
	}
	SaveUpdateCache(newCache)

	// Check if newer
	if latest != nil && IsNewerVersion(latest.Version, version.Version) {
		return latest, nil
	}

	return nil, nil
}

// IsBinaryInstall checks if the CLI was installed as a standalone binary.
func IsBinaryInstall() bool {
	// Check if executable is in a typical binary location
	exe, err := os.Executable()
	if err != nil {
		return false
	}

	// Resolve symlinks
	exe, err = filepath.EvalSymlinks(exe)
	if err != nil {
		return false
	}

	// Check if it's in standard binary directories
	dir := filepath.Dir(exe)
	binaryDirs := []string{"/usr/local/bin", "/usr/bin", "/opt/homebrew/bin"}
	for _, d := range binaryDirs {
		if dir == d {
			return true
		}
	}

	// Check HOME/bin or similar
	home := os.Getenv("HOME")
	if home != "" && strings.HasPrefix(dir, home) {
		return true
	}

	return true // Default to true for most cases
}

// GetCurrentExecutable returns the path to the current executable.
func GetCurrentExecutable() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	return filepath.EvalSymlinks(exe)
}

// DownloadBinary downloads a binary from URL to dest.
func DownloadBinary(url, dest string) error {
	client := &http.Client{
		Timeout: 60 * time.Second,
	}

	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download failed with status %d", resp.StatusCode)
	}

	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, resp.Body)
	return err
}

// PerformSelfUpdate performs self-update to the specified version.
func PerformSelfUpdate(info *VersionInfo) (bool, string) {
	if !IsBinaryInstall() {
		return false, "Self-update is only available for standalone binary installations.\n" +
			"Please update using: go install github.com/OpenMined/syfthub/cli/cmd/syft@latest\n" +
			"Or reinstall using the install script."
	}

	currentExe, err := GetCurrentExecutable()
	if err != nil {
		return false, fmt.Sprintf("Could not determine current executable path: %v", err)
	}

	// Create temp directory for download
	tmpDir, err := os.MkdirTemp("", "syft-update-")
	if err != nil {
		return false, fmt.Sprintf("Failed to create temp directory: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	newBinary := filepath.Join(tmpDir, "syft_new")

	// Download new binary
	if err := DownloadBinary(info.DownloadURL, newBinary); err != nil {
		return false, fmt.Sprintf("Failed to download new version: %v", err)
	}

	// Make executable
	if err := os.Chmod(newBinary, 0755); err != nil {
		return false, fmt.Sprintf("Failed to make binary executable: %v", err)
	}

	// Verify new binary works
	cmd := exec.Command(newBinary, "--version")
	if err := cmd.Run(); err != nil {
		return false, "Downloaded binary verification failed."
	}

	// Replace current binary
	if runtime.GOOS == "windows" {
		// On Windows, rename current to .old, copy new
		oldExe := currentExe + ".old"
		os.Remove(oldExe)
		if err := os.Rename(currentExe, oldExe); err != nil {
			return false, fmt.Sprintf("Failed to rename old binary: %v", err)
		}
		if err := copyFile(newBinary, currentExe); err != nil {
			// Try to restore old binary
			os.Rename(oldExe, currentExe)
			return false, fmt.Sprintf("Failed to install new binary: %v", err)
		}
	} else {
		// On Unix, try direct copy first
		if err := copyFile(newBinary, currentExe); err != nil {
			// Try with sudo
			cmd := exec.Command("sudo", "cp", newBinary, currentExe)
			if err := cmd.Run(); err != nil {
				return false, "Permission denied. Try running with sudo:\n  sudo syft upgrade"
			}
		}
	}

	// Update cache
	cache := LoadUpdateCache()
	if cache == nil {
		cache = &UpdateCache{}
	}
	cache.LatestVersion = info.Version
	cache.LastCheck = time.Now().UTC().Format(time.RFC3339)
	SaveUpdateCache(cache)

	return true, fmt.Sprintf("Successfully updated to v%s!", info.Version)
}

// copyFile copies a file from src to dst.
func copyFile(src, dst string) error {
	source, err := os.Open(src)
	if err != nil {
		return err
	}
	defer source.Close()

	dest, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer dest.Close()

	_, err = io.Copy(dest, source)
	if err != nil {
		return err
	}

	// Copy permissions
	srcInfo, err := os.Stat(src)
	if err != nil {
		return err
	}

	return os.Chmod(dst, srcInfo.Mode())
}

// GetUpdateNotification returns an update notification message if available.
func GetUpdateNotification() string {
	// Don't check if disabled via environment variable
	if env := os.Getenv("SYFT_NO_UPDATE_CHECK"); env != "" {
		lower := strings.ToLower(env)
		if lower == "1" || lower == "true" || lower == "yes" {
			return ""
		}
	}

	info, err := CheckForUpdates(false)
	if err != nil || info == nil {
		return ""
	}

	return fmt.Sprintf("\nA new version of syft is available: v%s -> v%s\n"+
		"Run 'syft upgrade' to update, or visit %s",
		version.Version, info.Version, info.ReleaseURL)
}
