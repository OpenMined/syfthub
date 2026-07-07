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

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
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
	locks      sync.Map // map[string]*sync.Mutex — per-hash locks for concurrent venv creation
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

// lockForHash returns a per-hash mutex, creating one if it doesn't exist yet.
// This allows concurrent venv creation for endpoints with different dependency sets
// while serializing operations on the same dependency hash.
func (m *VenvManager) lockForHash(key string) *sync.Mutex {
	val, _ := m.locks.LoadOrStore(key, &sync.Mutex{})
	return val.(*sync.Mutex)
}

// resolveDeps reads pyproject.toml or requirements.txt from endpointDir and
// returns the list of pip dependencies. extras selects optional-dependency
// groups from pyproject.toml.
func (m *VenvManager) resolveDeps(endpointDir string, extras []string) ([]string, error) {
	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	requirementsPath := filepath.Join(endpointDir, "requirements.txt")

	if _, statErr := os.Stat(pyprojectPath); statErr == nil {
		return m.parsePyprojectDeps(pyprojectPath, extras)
	}
	if _, statErr := os.Stat(requirementsPath); statErr == nil {
		return m.parseRequirementsTxt(requirementsPath)
	}
	return nil, nil
}

// EnsureVenv ensures a virtual environment exists for the given endpoint.
// Returns the path to the Python interpreter in the venv.
// additionalDeps are extra packages to install (e.g., "policy-manager" for policy enforcement).
func (m *VenvManager) EnsureVenv(endpointDir string, extras []string, additionalDeps ...string) (string, error) {
	deps, err := m.resolveDeps(endpointDir, extras)
	if err != nil {
		return "", err
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

	// Calculate hash of dependencies and lock per-hash
	hash := m.hashDeps(deps)
	mu := m.lockForHash(hash)
	mu.Lock()
	defer mu.Unlock()

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

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Section headers
		if line == "[project.dependencies]" {
			inDeps = true
			continue
		}
		if strings.HasPrefix(line, "[project.optional-dependencies.") {
			extra := strings.TrimSuffix(strings.TrimPrefix(line, "[project.optional-dependencies."), "]")
			inOptionalDeps = false
			for _, e := range extras {
				if e == extra {
					inOptionalDeps = true
					break
				}
			}
			continue
		}
		if strings.HasPrefix(line, "[") {
			inDeps = false
			inOptionalDeps = false
			continue
		}

		// Inline dependencies = [...] (handled via shared helper)
		if strings.HasPrefix(line, "dependencies = [") {
			if entries, ok := nodeops.ParseInlineDeps(line); ok {
				for _, entry := range entries {
					deps = append(deps, strings.Trim(entry, `"'`))
				}
				continue
			}
			// Multi-line array start
			inDeps = true
			continue
		}

		// Inline extras format: extra_name = ["dep1", "dep2"]
		for _, extra := range extras {
			prefix := extra + " = ["
			if strings.HasPrefix(line, prefix) && strings.Contains(line, "]") {
				inner := line[len(prefix):strings.Index(line, "]")]
				for _, dep := range strings.Split(inner, ",") {
					dep = strings.Trim(dep, `"' `)
					if dep != "" {
						deps = append(deps, dep)
					}
				}
			}
		}

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") || line == "]" {
			if line == "]" {
				inDeps = false
				inOptionalDeps = false
			}
			continue
		}

		// Multi-line array entries
		if inDeps || inOptionalDeps {
			dep := strings.Trim(line, `"',`)
			if dep != "" {
				deps = append(deps, dep)
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

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
