package filemode

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"
)

// venvPythonPath returns the path to the Python interpreter in a venv,
// accounting for platform differences (Windows vs Unix).
func venvPythonPath(venvDir string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(venvDir, "Scripts", "python.exe")
	}
	return filepath.Join(venvDir, "bin", "python")
}

// VenvManager manages Python virtual environments for endpoints.
type VenvManager struct {
	cacheDir   string
	pythonPath string
	logger     *slog.Logger
	mu         sync.Mutex
}

// VenvConfig holds venv manager configuration.
type VenvConfig struct {
	CacheDir   string
	PythonPath string
	Logger     *slog.Logger
}

// NewVenvManager creates a new venv manager.
func NewVenvManager(cfg *VenvConfig) (*VenvManager, error) {
	cacheDir := cfg.CacheDir
	if cacheDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("failed to get home directory: %w", err)
		}
		cacheDir = filepath.Join(home, ".cache", "syfthubapi", "venvs")
	}

	// Ensure cache directory exists
	if err := os.MkdirAll(cacheDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create cache directory: %w", err)
	}

	pythonPath := cfg.PythonPath
	if pythonPath == "" {
		// On Windows, "python3" often doesn't exist; use "python" instead
		if runtime.GOOS == "windows" {
			pythonPath = "python"
		} else {
			pythonPath = "python3"
		}
	}

	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &VenvManager{
		cacheDir:   cacheDir,
		pythonPath: pythonPath,
		logger:     logger,
	}, nil
}

// EnsureVenv ensures a virtual environment exists for the given endpoint.
// Returns the path to the Python interpreter in the venv.
// additionalDeps are extra packages to install (e.g., "policy-manager" for policy enforcement).
func (m *VenvManager) EnsureVenv(endpointDir string, extras []string, additionalDeps ...string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Check for pyproject.toml
	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	requirementsPath := filepath.Join(endpointDir, "requirements.txt")

	var deps []string
	var err error

	if _, statErr := os.Stat(pyprojectPath); statErr == nil {
		deps, err = m.parsePyprojectDeps(pyprojectPath, extras)
		if err != nil {
			return "", err
		}
	} else if _, statErr := os.Stat(requirementsPath); statErr == nil {
		deps, err = m.parseRequirementsTxt(requirementsPath)
		if err != nil {
			return "", err
		}
	}

	// Add additional dependencies (e.g., policy-manager for policy enforcement)
	deps = append(deps, additionalDeps...)

	// If no dependencies, just use system Python
	if len(deps) == 0 {
		m.logger.Debug("no dependencies, using system Python",
			"endpoint", filepath.Base(endpointDir),
		)
		return m.pythonPath, nil
	}

	// Calculate hash of dependencies
	hash := m.hashDeps(deps)
	venvDir := filepath.Join(m.cacheDir, hash)
	pythonPath := venvPythonPath(venvDir)

	// Check if venv already exists
	if _, err := os.Stat(pythonPath); err == nil {
		m.logger.Debug("using cached venv",
			"endpoint", filepath.Base(endpointDir),
			"hash", hash[:8],
		)
		return pythonPath, nil
	}

	// Create venv
	m.logger.Info("creating venv",
		"endpoint", filepath.Base(endpointDir),
		"deps", len(deps),
	)

	if err := m.createVenv(venvDir); err != nil {
		return "", err
	}

	// Install dependencies
	if err := m.installDeps(pythonPath, deps); err != nil {
		// Clean up on failure
		os.RemoveAll(venvDir)
		return "", err
	}

	m.logger.Info("venv created",
		"endpoint", filepath.Base(endpointDir),
		"hash", hash[:8],
	)

	return pythonPath, nil
}

// EnsureLocalVenv creates a venv in the endpoint directory itself.
func (m *VenvManager) EnsureLocalVenv(endpointDir string, extras []string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	venvDir := filepath.Join(endpointDir, ".venv")
	pythonPath := venvPythonPath(venvDir)

	// Check if venv already exists
	if _, err := os.Stat(pythonPath); err == nil {
		return pythonPath, nil
	}

	// Check for dependencies
	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	requirementsPath := filepath.Join(endpointDir, "requirements.txt")

	var deps []string
	var err error

	if _, statErr := os.Stat(pyprojectPath); statErr == nil {
		deps, err = m.parsePyprojectDeps(pyprojectPath, extras)
		if err != nil {
			return "", err
		}
	} else if _, statErr := os.Stat(requirementsPath); statErr == nil {
		deps, err = m.parseRequirementsTxt(requirementsPath)
		if err != nil {
			return "", err
		}
	}

	// Create venv
	m.logger.Info("creating local venv",
		"endpoint", filepath.Base(endpointDir),
	)

	if err := m.createVenv(venvDir); err != nil {
		return "", err
	}

	// Install dependencies
	if len(deps) > 0 {
		if err := m.installDeps(pythonPath, deps); err != nil {
			return "", err
		}
	}

	return pythonPath, nil
}

// createVenv creates a new virtual environment.
func (m *VenvManager) createVenv(venvDir string) error {
	cmd := exec.Command(m.pythonPath, "-m", "venv", venvDir)
	hideWindow(cmd)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("failed to create venv: %w\n%s", err, string(output))
	}
	return nil
}

// installDeps installs dependencies into a venv.
func (m *VenvManager) installDeps(pythonPath string, deps []string) error {
	// Upgrade pip first
	cmd := exec.Command(pythonPath, "-m", "pip", "install", "--upgrade", "pip")
	hideWindow(cmd)
	if output, err := cmd.CombinedOutput(); err != nil {
		m.logger.Warn("failed to upgrade pip", "error", err, "output", string(output))
	}

	// Install dependencies
	args := append([]string{"-m", "pip", "install", "-q"}, deps...)
	cmd = exec.Command(pythonPath, args...)
	hideWindow(cmd)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("failed to install dependencies: %w\n%s", err, string(output))
	}

	return nil
}

// parsePyprojectDeps parses dependencies from pyproject.toml.
func (m *VenvManager) parsePyprojectDeps(path string, extras []string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var deps []string
	scanner := bufio.NewScanner(file)
	inDeps := false
	inOptionalDeps := false
	currentExtra := ""

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Check for section headers
		if line == "[project.dependencies]" || line == "dependencies = [" {
			inDeps = true
			continue
		}
		if strings.HasPrefix(line, "[project.optional-dependencies") || strings.HasPrefix(line, "[tool.") {
			inDeps = false
		}
		if strings.HasPrefix(line, "[project.optional-dependencies.") {
			extra := strings.TrimSuffix(strings.TrimPrefix(line, "[project.optional-dependencies."), "]")
			for _, e := range extras {
				if e == extra {
					inOptionalDeps = true
					currentExtra = extra
					break
				}
			}
			continue
		}
		if strings.HasPrefix(line, "[") && !strings.HasPrefix(line, "[project.optional-dependencies") {
			inOptionalDeps = false
			currentExtra = ""
		}

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		// Parse dependency line
		if inDeps || inOptionalDeps {
			// Handle TOML array format
			dep := strings.Trim(line, `"',[]`)
			if dep != "" && !strings.HasPrefix(dep, "#") {
				deps = append(deps, dep)
			}
		}

		// Simple inline dependencies format
		if strings.HasPrefix(line, "dependencies = [") && strings.HasSuffix(line, "]") {
			content := strings.TrimPrefix(line, "dependencies = [")
			content = strings.TrimSuffix(content, "]")
			for _, dep := range strings.Split(content, ",") {
				dep = strings.Trim(dep, `"' `)
				if dep != "" {
					deps = append(deps, dep)
				}
			}
		}

		// Check for extras inline format
		for _, extra := range extras {
			prefix := fmt.Sprintf("%s = [", extra)
			if strings.HasPrefix(line, prefix) && strings.HasSuffix(line, "]") {
				content := strings.TrimPrefix(line, prefix)
				content = strings.TrimSuffix(content, "]")
				for _, dep := range strings.Split(content, ",") {
					dep = strings.Trim(dep, `"' `)
					if dep != "" {
						deps = append(deps, dep)
					}
				}
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	_ = currentExtra // Avoid unused variable warning

	return deps, nil
}

// parseRequirementsTxt parses dependencies from requirements.txt.
func (m *VenvManager) parseRequirementsTxt(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var deps []string
	scanner := bufio.NewScanner(file)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		// Skip editable installs and file references for now
		if strings.HasPrefix(line, "-e") || strings.HasPrefix(line, "-r") {
			continue
		}

		deps = append(deps, line)
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return deps, nil
}

// hashDeps creates a hash of the dependencies for caching.
func (m *VenvManager) hashDeps(deps []string) string {
	// Sort for consistent hashing
	sorted := make([]string, len(deps))
	copy(sorted, deps)
	sort.Strings(sorted)

	h := sha256.New()
	for _, dep := range sorted {
		h.Write([]byte(dep))
		h.Write([]byte("\n"))
	}

	return hex.EncodeToString(h.Sum(nil))
}

// CleanupOldVenvs removes venvs that haven't been used recently.
func (m *VenvManager) CleanupOldVenvs(maxAge int64) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	entries, err := os.ReadDir(m.cacheDir)
	if err != nil {
		return err
	}

	now := time.Now().Unix()
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		path := filepath.Join(m.cacheDir, entry.Name())
		info, err := entry.Info()
		if err != nil {
			continue
		}

		age := now - info.ModTime().Unix()
		if age > maxAge {
			m.logger.Info("removing old venv",
				"name", entry.Name(),
				"age_days", age/86400,
			)
			os.RemoveAll(path)
		}
	}

	return nil
}
