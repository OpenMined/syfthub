package filemode

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

// PythonVersion is the version of Python to download.
const PythonVersion = "3.13.1"

// PythonBuildTag is the python-build-standalone release tag.
const PythonBuildTag = "20241206"

// EmbeddedPythonManager manages a standalone Python installation.
type EmbeddedPythonManager struct {
	baseDir    string
	logger     *slog.Logger
	mu         sync.Mutex
	pythonPath string
}

// EmbeddedPythonConfig holds configuration for the embedded Python manager.
type EmbeddedPythonConfig struct {
	BaseDir string
	Logger  *slog.Logger
}

// PythonBuild represents a downloadable Python build.
type PythonBuild struct {
	URL         string
	Checksum    string // SHA256
	ArchiveType string // "tar.gz" or "zip"
}

// getPythonBuilds returns the download URLs for different platforms.
// Using python-build-standalone releases: https://github.com/indygreg/python-build-standalone
func getPythonBuilds() map[string]PythonBuild {
	baseURL := fmt.Sprintf(
		"https://github.com/indygreg/python-build-standalone/releases/download/%s",
		PythonBuildTag,
	)

	return map[string]PythonBuild{
		// Windows x64
		"windows-amd64": {
			URL: fmt.Sprintf("%s/cpython-%s+%s-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
				baseURL, PythonVersion, PythonBuildTag),
			ArchiveType: "tar.gz",
		},
		// Linux x64
		"linux-amd64": {
			URL: fmt.Sprintf("%s/cpython-%s+%s-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
				baseURL, PythonVersion, PythonBuildTag),
			ArchiveType: "tar.gz",
		},
		// Linux ARM64
		"linux-arm64": {
			URL: fmt.Sprintf("%s/cpython-%s+%s-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
				baseURL, PythonVersion, PythonBuildTag),
			ArchiveType: "tar.gz",
		},
		// macOS x64
		"darwin-amd64": {
			URL: fmt.Sprintf("%s/cpython-%s+%s-x86_64-apple-darwin-install_only_stripped.tar.gz",
				baseURL, PythonVersion, PythonBuildTag),
			ArchiveType: "tar.gz",
		},
		// macOS ARM64 (Apple Silicon)
		"darwin-arm64": {
			URL: fmt.Sprintf("%s/cpython-%s+%s-aarch64-apple-darwin-install_only_stripped.tar.gz",
				baseURL, PythonVersion, PythonBuildTag),
			ArchiveType: "tar.gz",
		},
	}
}

// NewEmbeddedPythonManager creates a new embedded Python manager.
func NewEmbeddedPythonManager(cfg *EmbeddedPythonConfig) (*EmbeddedPythonManager, error) {
	baseDir := cfg.BaseDir
	if baseDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("failed to get home directory: %w", err)
		}
		baseDir = filepath.Join(home, ".cache", "syfthubapi", "python")
	}

	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &EmbeddedPythonManager{
		baseDir: baseDir,
		logger:  logger,
	}, nil
}

// EnsurePython ensures a standalone Python is available.
// Returns the path to the Python executable.
func (m *EmbeddedPythonManager) EnsurePython(ctx context.Context) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Check if already resolved
	if m.pythonPath != "" {
		return m.pythonPath, nil
	}

	// Determine expected Python path
	pythonPath := m.getPythonExecutablePath()

	// Check if Python already exists
	if _, err := os.Stat(pythonPath); err == nil {
		m.logger.Info("using embedded Python",
			"version", PythonVersion,
			"path", pythonPath,
		)
		m.pythonPath = pythonPath
		return pythonPath, nil
	}

	// Need to download Python
	m.logger.Info("embedded Python not found, downloading...",
		"version", PythonVersion,
	)

	if err := m.downloadPython(ctx); err != nil {
		return "", fmt.Errorf("failed to download Python: %w", err)
	}

	// Verify Python is now available
	if _, err := os.Stat(pythonPath); err != nil {
		return "", fmt.Errorf("python executable not found after download: %s", pythonPath)
	}

	m.logger.Info("embedded Python ready",
		"version", PythonVersion,
		"path", pythonPath,
	)
	m.pythonPath = pythonPath
	return pythonPath, nil
}

// getPythonExecutablePath returns the expected path to the Python executable.
func (m *EmbeddedPythonManager) getPythonExecutablePath() string {
	versionDir := filepath.Join(m.baseDir, PythonVersion)

	if runtime.GOOS == "windows" {
		return filepath.Join(versionDir, "python", "python.exe")
	}
	return filepath.Join(versionDir, "python", "bin", "python3")
}

// GetPythonPath returns the cached Python path if available.
func (m *EmbeddedPythonManager) GetPythonPath() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.pythonPath
}

// downloadPython downloads and extracts the Python build.
func (m *EmbeddedPythonManager) downloadPython(ctx context.Context) error {
	// Get platform key
	platformKey := fmt.Sprintf("%s-%s", runtime.GOOS, runtime.GOARCH)
	builds := getPythonBuilds()

	build, ok := builds[platformKey]
	if !ok {
		return fmt.Errorf("unsupported platform: %s", platformKey)
	}

	// Create version directory
	versionDir := filepath.Join(m.baseDir, PythonVersion)
	if err := os.MkdirAll(versionDir, 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	// Download archive
	archivePath := filepath.Join(versionDir, "python.tar.gz")
	if err := m.downloadFile(ctx, build.URL, archivePath); err != nil {
		return fmt.Errorf("failed to download: %w", err)
	}

	// Extract archive
	m.logger.Info("extracting Python...")
	if err := m.extractTarGz(archivePath, versionDir); err != nil {
		os.Remove(archivePath)
		return fmt.Errorf("failed to extract: %w", err)
	}

	// Clean up archive
	os.Remove(archivePath)

	return nil
}

// downloadFile downloads a file from URL to destination.
func (m *EmbeddedPythonManager) downloadFile(ctx context.Context, url, dest string) error {
	m.logger.Info("downloading Python",
		"url", url,
		"dest", dest,
	)

	// Create HTTP request with context
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}

	// Create HTTP client with timeout
	client := &http.Client{
		Timeout: 10 * time.Minute, // Large file, generous timeout
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP error: %s", resp.Status)
	}

	// Create destination file
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()

	// Copy with progress logging
	size := resp.ContentLength
	written := int64(0)
	lastLog := time.Now()

	reader := &progressReader{
		reader: resp.Body,
		onProgress: func(n int64) {
			written += n
			if time.Since(lastLog) > 5*time.Second {
				if size > 0 {
					pct := float64(written) / float64(size) * 100
					m.logger.Info("download progress",
						"percent", fmt.Sprintf("%.1f%%", pct),
						"bytes", written,
					)
				}
				lastLog = time.Now()
			}
		},
	}

	_, err = io.Copy(out, reader)
	if err != nil {
		return err
	}

	m.logger.Info("download complete",
		"bytes", written,
	)

	return nil
}

// extractTarGz extracts a .tar.gz archive.
func (m *EmbeddedPythonManager) extractTarGz(archivePath, destDir string) error {
	file, err := os.Open(archivePath)
	if err != nil {
		return err
	}
	defer file.Close()

	gzr, err := gzip.NewReader(file)
	if err != nil {
		return err
	}
	defer gzr.Close()

	tr := tar.NewReader(gzr)

	for {
		header, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}

		// Sanitize path to prevent directory traversal
		target := filepath.Join(destDir, header.Name)
		if !strings.HasPrefix(target, filepath.Clean(destDir)+string(os.PathSeparator)) {
			return fmt.Errorf("invalid tar path: %s", header.Name)
		}

		switch header.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, 0755); err != nil {
				return err
			}
		case tar.TypeReg:
			// Ensure parent directory exists
			if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
				return err
			}

			// Create file
			outFile, err := os.OpenFile(target, os.O_CREATE|os.O_RDWR|os.O_TRUNC, os.FileMode(header.Mode))
			if err != nil {
				return err
			}

			if _, err := io.Copy(outFile, tr); err != nil {
				outFile.Close()
				return err
			}
			outFile.Close()

		case tar.TypeSymlink:
			// Handle symlinks (important for Unix Python installations)
			if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
				return err
			}
			// Remove existing symlink if present
			os.Remove(target)
			if err := os.Symlink(header.Linkname, target); err != nil {
				// On Windows, symlinks might fail - continue anyway
				if runtime.GOOS != "windows" {
					m.logger.Warn("failed to create symlink",
						"target", target,
						"link", header.Linkname,
						"error", err,
					)
				}
			}
		}
	}

	return nil
}

// Verify checks if the embedded Python works correctly.
func (m *EmbeddedPythonManager) Verify(ctx context.Context) error {
	pythonPath, err := m.EnsurePython(ctx)
	if err != nil {
		return err
	}

	// Try running python --version
	cmd := exec.CommandContext(ctx, pythonPath, "--version")
	hideWindow(cmd)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("python verification failed: %w\n%s", err, string(output))
	}

	m.logger.Debug("Python verified",
		"output", strings.TrimSpace(string(output)),
	)

	return nil
}

// Checksum calculates SHA256 checksum of a file.
func (m *EmbeddedPythonManager) Checksum(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}

	return hex.EncodeToString(h.Sum(nil)), nil
}

// progressReader wraps a reader to track progress.
type progressReader struct {
	reader     io.Reader
	onProgress func(n int64)
}

func (r *progressReader) Read(p []byte) (int, error) {
	n, err := r.reader.Read(p)
	if r.onProgress != nil && n > 0 {
		r.onProgress(int64(n))
	}
	return n, err
}
