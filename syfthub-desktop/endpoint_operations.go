// Package main provides endpoint file operations for the SyftHub Desktop GUI.
// These methods enable reading and writing endpoint files (runner.py, README.md, .env, etc.)
package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	goruntime "runtime"
	"strings"

	"github.com/wailsapp/wails/v2/pkg/runtime"
	"gopkg.in/yaml.v3"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// EndpointDetail provides full endpoint information for the detail view.
type EndpointDetail struct {
	Slug            string           `json:"slug"`
	Name            string           `json:"name"`
	Description     string           `json:"description"`
	Type            string           `json:"type"`
	Version         string           `json:"version"`
	Enabled         bool             `json:"enabled"`
	HasReadme       bool             `json:"hasReadme"`
	HasPolicies     bool             `json:"hasPolicies"`
	DepsCount       int              `json:"depsCount"`
	EnvCount        int              `json:"envCount"`
	RunnerCode      string           `json:"runnerCode"`
	ReadmeContent   string           `json:"readmeContent"`
	Policies    []Policy         `json:"policies"`
	SetupStatus     *SetupStatusInfo `json:"setupStatus,omitempty"`
	SetupSpec       *SetupSpecInfo   `json:"setupSpec,omitempty"`
}

// EnvVar represents an environment variable.
type EnvVar struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

// Dependency represents a Python package dependency.
type Dependency struct {
	Package string `json:"package"`
	Version string `json:"version"`
}

// Policy represents a single policy configuration.
type Policy struct {
	Name   string                 `json:"name" yaml:"name"`
	Type   string                 `json:"type" yaml:"type"`
	Config map[string]interface{} `json:"config" yaml:"config"`
}

func fromNodeopsEnvVars(vs []nodeops.EnvVar) []EnvVar {
	out := make([]EnvVar, len(vs))
	for i, v := range vs {
		out[i] = EnvVar{Key: v.Key, Value: v.Value}
	}
	return out
}

func toNodeopsEnvVars(vs []EnvVar) []nodeops.EnvVar {
	out := make([]nodeops.EnvVar, len(vs))
	for i, v := range vs {
		out[i] = nodeops.EnvVar{Key: v.Key, Value: v.Value}
	}
	return out
}

func fromNodeopsDeps(ds []nodeops.Dependency) []Dependency {
	out := make([]Dependency, len(ds))
	for i, d := range ds {
		out[i] = Dependency{Package: d.Package, Version: d.Version}
	}
	return out
}

// GetEndpointDetail returns full details for an endpoint.
func (a *App) GetEndpointDetail(slug string) (*EndpointDetail, error) {
	runtime.LogDebug(a.ctx, fmt.Sprintf("GetEndpointDetail called for slug: %s", slug))

	config, err := a.getConfig()
	if err != nil {
		runtime.LogError(a.ctx, "GetEndpointDetail: app not configured")
		return nil, err
	}

	runtime.LogDebug(a.ctx, fmt.Sprintf("GetEndpointDetail: endpoints path = %s", config.EndpointsPath))

	endpointDir := filepath.Join(config.EndpointsPath, slug)
	runtime.LogDebug(a.ctx, fmt.Sprintf("GetEndpointDetail: looking for endpoint at %s", endpointDir))

	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		runtime.LogError(a.ctx, fmt.Sprintf("GetEndpointDetail: endpoint not found at %s", endpointDir))
		return nil, fmt.Errorf("endpoint not found: %s", slug)
	}

	// Initialize detail with defaults
	detail := &EndpointDetail{
		Slug:    slug,
		Name:    slug, // Default to slug
		Type:    "model",
		Version: "1.0.0",
		Enabled: true,
	}

	// Parse README.md frontmatter for metadata (single source of truth)
	readmePath := filepath.Join(endpointDir, "README.md")
	if content, err := os.ReadFile(readmePath); err == nil {
		detail.HasReadme = true
		detail.ReadmeContent = string(content)

		// Parse frontmatter from already-loaded content (avoids re-opening the file).
		if frontmatter, _, err := nodeops.ParseReadmeFrontmatterBytes(content); err == nil {
			if frontmatter.Name != "" {
				detail.Name = frontmatter.Name
			}
			if frontmatter.Slug != "" {
				detail.Slug = frontmatter.Slug
			}
			if frontmatter.Description != "" {
				detail.Description = frontmatter.Description
			}
			if frontmatter.Type != "" {
				detail.Type = frontmatter.Type
			}
			if frontmatter.Version != "" {
				detail.Version = frontmatter.Version
			}
			if frontmatter.Enabled != nil {
				detail.Enabled = *frontmatter.Enabled
			}
		} else {
			runtime.LogWarning(a.ctx, fmt.Sprintf("Failed to parse README.md frontmatter: %v", err))
		}
	}

	// Read runner.py
	runnerPath := filepath.Join(endpointDir, "runner.py")
	if content, err := os.ReadFile(runnerPath); err == nil {
		detail.RunnerCode = string(content)
	}

	// Load policies from the policy/ directory — the format read by the execution engine.
	policyDir := filepath.Join(endpointDir, "policy")
	if entries, err := os.ReadDir(policyDir); err == nil {
		for _, e := range entries {
			if e.IsDir() {
				continue
			}
			if ext := filepath.Ext(e.Name()); ext != ".yaml" && ext != ".yml" {
				continue
			}
			content, err := os.ReadFile(filepath.Join(policyDir, e.Name()))
			if err != nil {
				continue
			}
			var p Policy
			if err := yaml.Unmarshal(content, &p); err != nil || p.Name == "" {
				continue
			}
			detail.Policies = append(detail.Policies, p)
		}
		detail.HasPolicies = len(detail.Policies) > 0
	}

	// Count environment variables
	envPath := filepath.Join(endpointDir, ".env")
	if envVars, err := a.readEnvFile(envPath); err == nil {
		detail.EnvCount = len(envVars)
	}

	// Count dependencies from pyproject.toml
	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	if deps, err := a.readDependencies(pyprojectPath); err == nil {
		detail.DepsCount = len(deps)
	}

	// Load setup spec and status (read state once, share across both conversions)
	setupPath := filepath.Join(endpointDir, "setup.yaml")
	if spec, err := nodeops.ParseSetupYaml(setupPath); err == nil && spec != nil {
		state, _ := nodeops.ReadSetupState(endpointDir)
		detail.SetupSpec = toSetupSpecInfoFromState(spec, state)
		detail.SetupStatus = toSetupStatusInfo(nodeops.ComputeSetupStatus(spec, state))
	}

	runtime.LogDebug(a.ctx, fmt.Sprintf("GetEndpointDetail: returning detail for %s (name=%s, type=%s, enabled=%v, hasRunner=%v, hasReadme=%v)",
		slug, detail.Name, detail.Type, detail.Enabled, len(detail.RunnerCode) > 0, detail.HasReadme))

	return detail, nil
}


// GetRunnerCode returns the runner.py content for an endpoint.
func (a *App) GetRunnerCode(slug string) (string, error) {
	config, err := a.getConfig()
	if err != nil {
		return "", err
	}

	runnerPath := filepath.Join(config.EndpointsPath, slug, "runner.py")
	content, err := os.ReadFile(runnerPath)
	if err != nil {
		return "", fmt.Errorf("failed to read runner.py: %w", err)
	}

	return string(content), nil
}

// SaveRunnerCode saves the runner.py content for an endpoint.
func (a *App) SaveRunnerCode(slug, code string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	runnerPath := filepath.Join(config.EndpointsPath, slug, "runner.py")
	if err := os.WriteFile(runnerPath, []byte(code), 0644); err != nil {
		return fmt.Errorf("failed to save runner.py: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Saved runner.py for endpoint: %s", slug))
	return nil
}

// GetReadme returns the README.md content for an endpoint.
func (a *App) GetReadme(slug string) (string, error) {
	config, err := a.getConfig()
	if err != nil {
		return "", err
	}

	readmePath := filepath.Join(config.EndpointsPath, slug, "README.md")
	content, err := os.ReadFile(readmePath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil // Return empty string if README doesn't exist
		}
		return "", fmt.Errorf("failed to read README.md: %w", err)
	}

	return string(content), nil
}

// SaveReadme saves the README.md content for an endpoint.
func (a *App) SaveReadme(slug, content string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	readmePath := filepath.Join(config.EndpointsPath, slug, "README.md")
	if err := os.WriteFile(readmePath, []byte(content), 0644); err != nil {
		return fmt.Errorf("failed to save README.md: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Saved README.md for endpoint: %s", slug))
	return nil
}

// GetEnvironment returns environment variables for an endpoint.
func (a *App) GetEnvironment(slug string) ([]EnvVar, error) {
	config, err := a.getConfig()
	if err != nil {
		return nil, err
	}

	envPath := filepath.Join(config.EndpointsPath, slug, ".env")
	return a.readEnvFile(envPath)
}

// readEnvFile reads a .env file and returns key-value pairs.
func (a *App) readEnvFile(path string) ([]EnvVar, error) {
	nVars, err := nodeops.ReadEnvFile(path)
	if err != nil {
		return nil, err
	}
	return fromNodeopsEnvVars(nVars), nil
}

// SetEnvironment adds or updates an environment variable.
func (a *App) SetEnvironment(slug, key, value string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	envPath := filepath.Join(config.EndpointsPath, slug, ".env")

	// Read existing vars
	vars, err := a.readEnvFile(envPath)
	if err != nil && !os.IsNotExist(err) {
		return err
	}

	// Update or add the variable
	found := false
	for i, v := range vars {
		if v.Key == key {
			vars[i].Value = value
			found = true
			break
		}
	}
	if !found {
		vars = append(vars, EnvVar{Key: key, Value: value})
	}

	// Write back
	return a.writeEnvFile(envPath, vars)
}

// DeleteEnvironment removes an environment variable.
func (a *App) DeleteEnvironment(slug, key string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	envPath := filepath.Join(config.EndpointsPath, slug, ".env")

	// Read existing vars
	vars, err := a.readEnvFile(envPath)
	if err != nil {
		return err
	}

	// Remove the variable
	var newVars []EnvVar
	for _, v := range vars {
		if v.Key != key {
			newVars = append(newVars, v)
		}
	}

	// Write back
	return a.writeEnvFile(envPath, newVars)
}

// writeEnvFile writes environment variables to a .env file.
func (a *App) writeEnvFile(path string, vars []EnvVar) error {
	return nodeops.WriteEnvFile(path, toNodeopsEnvVars(vars))
}

// GetDependencies returns Python dependencies for an endpoint.
func (a *App) GetDependencies(slug string) ([]Dependency, error) {
	config, err := a.getConfig()
	if err != nil {
		return nil, err
	}

	pyprojectPath := filepath.Join(config.EndpointsPath, slug, "pyproject.toml")
	return a.readDependencies(pyprojectPath)
}

// readDependencies reads dependencies from pyproject.toml.
func (a *App) readDependencies(path string) ([]Dependency, error) {
	nDeps, err := nodeops.ReadDependencies(path)
	if err != nil {
		return nil, err
	}
	return fromNodeopsDeps(nDeps), nil
}

// AddDependency adds a dependency to the endpoint's pyproject.toml.
func (a *App) AddDependency(slug, pkg, version string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	if pkg == "" {
		return fmt.Errorf("package name is required")
	}

	pyprojectPath := filepath.Join(config.EndpointsPath, slug, "pyproject.toml")

	// Check for duplicate before modifying the file
	existing, _ := a.readDependencies(pyprojectPath)
	for _, dep := range existing {
		if strings.EqualFold(dep.Package, pkg) {
			return fmt.Errorf("dependency already exists: %s", pkg)
		}
	}

	// Read existing content or create new
	content, err := os.ReadFile(pyprojectPath)
	if err != nil && !os.IsNotExist(err) {
		return err
	}

	lines := strings.Split(string(content), "\n")
	var newLines []string
	foundDeps := false
	addedDep := false

	// Format the dependency string
	depStr := pkg
	if version != "" {
		depStr = fmt.Sprintf("%s>=%s", pkg, version)
	}

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)

		// Found dependencies array start
		if strings.HasPrefix(trimmed, "dependencies = [") {
			foundDeps = true

			// Check if the array is closed on the same line (inline format)
			if entries, ok := nodeops.ParseInlineDeps(trimmed); ok {
				// Expand inline array to multi-line and append the new dep
				newLines = append(newLines, "dependencies = [")
				for _, entry := range entries {
					newLines = append(newLines, fmt.Sprintf("    %s,", entry))
				}
				newLines = append(newLines, fmt.Sprintf("    \"%s\",", depStr))
				newLines = append(newLines, "]")
				addedDep = true
				continue
			}

			newLines = append(newLines, line)
			continue
		}

		// Inside multi-line array, looking for closing bracket
		if foundDeps && !addedDep {
			if trimmed == "]" {
				newLines = append(newLines, fmt.Sprintf("    \"%s\",", depStr))
				addedDep = true
			}
		}

		// [project.dependencies] section: add before next section header
		if foundDeps && !addedDep && strings.HasPrefix(trimmed, "[") {
			newLines = append(newLines, fmt.Sprintf("\"%s\"", depStr))
			addedDep = true
		}

		newLines = append(newLines, line)

		if trimmed == "[project.dependencies]" {
			foundDeps = true
		}
	}

	// If in section format and reached end of file without another section
	if foundDeps && !addedDep {
		newLines = append(newLines, fmt.Sprintf("\"%s\"", depStr))
		addedDep = true
	}

	// If no dependencies section found, create one
	if !foundDeps {
		hasProject := false
		for _, line := range newLines {
			if strings.TrimSpace(line) == "[project]" {
				hasProject = true
				break
			}
		}

		if !hasProject {
			newLines = append([]string{"[project]", fmt.Sprintf("dependencies = [\"%s\"]", depStr), ""}, newLines...)
		} else {
			var insertLines []string
			inserted := false
			for _, line := range newLines {
				insertLines = append(insertLines, line)
				if strings.TrimSpace(line) == "[project]" && !inserted {
					insertLines = append(insertLines, fmt.Sprintf("dependencies = [\"%s\"]", depStr))
					inserted = true
				}
			}
			newLines = insertLines
		}
		addedDep = true
	}

	if !addedDep {
		return fmt.Errorf("failed to add dependency")
	}

	return os.WriteFile(pyprojectPath, []byte(strings.Join(newLines, "\n")), 0644)
}

// DeleteDependency removes a dependency from the endpoint's pyproject.toml.
func (a *App) DeleteDependency(slug, pkg string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	if pkg == "" {
		return fmt.Errorf("package name is required")
	}

	pyprojectPath := filepath.Join(config.EndpointsPath, slug, "pyproject.toml")

	content, err := os.ReadFile(pyprojectPath)
	if err != nil {
		return err
	}

	lines := strings.Split(string(content), "\n")
	var newLines []string
	inDeps := false
	deleted := false

	// Regex to match the package name at start of dependency
	pkgRegex := regexp.MustCompile(`^["']?` + regexp.QuoteMeta(pkg) + `([><=!~\[]|["'],?$)`)

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)

		// Track if we're in dependencies section
		if strings.HasPrefix(trimmed, "dependencies = [") {
			// Handle inline format: dependencies = ["numpy", "pandas"]
			if entries, ok := nodeops.ParseInlineDeps(trimmed); ok {
				var kept []string
				for _, entry := range entries {
					if nodeops.MatchesDep(entry, pkg) {
						deleted = true
						continue
					}
					kept = append(kept, entry)
				}
				if len(kept) == 0 {
					newLines = append(newLines, "dependencies = []")
				} else {
					newLines = append(newLines, fmt.Sprintf("dependencies = [%s]", strings.Join(kept, ", ")))
				}
				continue
			}
			inDeps = true
			newLines = append(newLines, line)
			continue
		}

		if trimmed == "[project.dependencies]" {
			inDeps = true
			newLines = append(newLines, line)
			continue
		}

		if inDeps && (trimmed == "]" || (strings.HasPrefix(trimmed, "[") && trimmed != "[project.dependencies]")) {
			if trimmed != "]" {
				inDeps = false
			}
			newLines = append(newLines, line)
			continue
		}

		// Check if this line contains the package to delete
		if inDeps && pkgRegex.MatchString(trimmed) {
			deleted = true
			continue // Skip this line
		}

		newLines = append(newLines, line)
	}

	if !deleted {
		return fmt.Errorf("dependency not found: %s", pkg)
	}

	return os.WriteFile(pyprojectPath, []byte(strings.Join(newLines, "\n")), 0644)
}

// UpdateEndpointOverview updates the endpoint overview fields in README.md frontmatter.
func (a *App) UpdateEndpointOverview(slug string, name, description, endpointType, version string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	readmePath := filepath.Join(config.EndpointsPath, slug, "README.md")

	// Update README.md frontmatter
	updates := map[string]interface{}{
		"name":        name,
		"description": description,
		"type":        endpointType,
		"version":     version,
	}

	if err := nodeops.UpdateReadmeFrontmatter(readmePath, updates); err != nil {
		return fmt.Errorf("failed to update README.md frontmatter: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Updated endpoint overview: %s", slug))
	return nil
}

// ToggleEndpointEnabled toggles the enabled status of an endpoint.
// This uses a fast path that updates the registry directly without recreating executors.
func (a *App) ToggleEndpointEnabled(slug string) (bool, error) {
	config, err := a.getConfig()
	if err != nil {
		return false, err
	}

	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()

	readmePath := filepath.Join(config.EndpointsPath, slug, "README.md")

	// Read current state from README.md frontmatter
	frontmatter, _, err := nodeops.ParseReadmeFrontmatter(readmePath)
	if err != nil {
		return false, fmt.Errorf("failed to read README.md: %w", err)
	}

	// Get current enabled state (default to true if not set)
	currentEnabled := true
	if frontmatter.Enabled != nil {
		currentEnabled = *frontmatter.Enabled
	}

	// Toggle
	newEnabled := !currentEnabled

	// Update README.md frontmatter (persists the change to disk)
	updates := map[string]interface{}{
		"enabled": newEnabled,
	}
	if err := nodeops.UpdateReadmeFrontmatter(readmePath, updates); err != nil {
		return false, fmt.Errorf("failed to update README.md frontmatter: %w", err)
	}

	// Fast path: Update registry directly without recreating executors (O(1) operation)
	// This avoids the expensive full reload which recreates all venvs and executors
	if core != nil {
		if !core.SetEndpointEnabled(slug, newEnabled) {
			runtime.LogWarning(a.ctx, fmt.Sprintf("Endpoint %s not found in registry, will be updated on next reload", slug))
		}
		// Trigger async sync to SyftHub (non-blocking)
		core.SyncEndpointsAsync()
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Toggled endpoint %s enabled: %v", slug, newEnabled))
	return newEnabled, nil
}

// openInExplorer opens the given path in the native file explorer.
func openInExplorer(path string) error {
	var cmd *exec.Cmd
	switch goruntime.GOOS {
	case "windows":
		cmd = exec.Command("explorer", path)
	case "darwin":
		cmd = exec.Command("open", path)
	default: // Linux and others
		cmd = exec.Command("xdg-open", path)
	}
	return cmd.Start()
}

// OpenEndpointsFolder opens the endpoints directory in the system file explorer.
func (a *App) OpenEndpointsFolder() error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	// Check if the directory exists
	if _, err := os.Stat(config.EndpointsPath); os.IsNotExist(err) {
		return fmt.Errorf("endpoints folder does not exist: %s", config.EndpointsPath)
	}

	return openInExplorer(config.EndpointsPath)
}

// OpenEndpointFolder opens a specific endpoint directory in the file explorer.
func (a *App) OpenEndpointFolder(slug string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	endpointPath := filepath.Join(config.EndpointsPath, slug)

	// Check if the directory exists
	if _, err := os.Stat(endpointPath); os.IsNotExist(err) {
		return fmt.Errorf("endpoint folder does not exist: %s", endpointPath)
	}

	return openInExplorer(endpointPath)
}

// validateYAML checks that a string contains valid YAML syntax.
func validateYAML(content string) error {
	var v interface{}
	if err := yaml.Unmarshal([]byte(content), &v); err != nil {
		return fmt.Errorf("invalid YAML syntax: %w", err)
	}
	return nil
}

// PolicyFileInfo represents a policy file in the policy directory.
type PolicyFileInfo struct {
	Filename string `json:"filename"`
	Name     string `json:"name"`
	Type     string `json:"type"`
}

// NewPolicyRequest contains the parameters for creating a new policy file.
type NewPolicyRequest struct {
	Name          string   `json:"name"`          // Display name for the policy
	Type          string   `json:"type"`          // Policy type (e.g., "AccessGroupPolicy")
	ChildPolicies []string `json:"childPolicies"` // For composite policies (AllOf, AnyOf, Not)
	DenyReason    string   `json:"denyReason"`    // For NotPolicy
}

// ListPolicyFiles returns all policy files in the endpoint's policy/ directory.
func (a *App) ListPolicyFiles(slug string) ([]PolicyFileInfo, error) {
	config, err := a.getConfig()
	if err != nil {
		return nil, err
	}

	policyDir := filepath.Join(config.EndpointsPath, slug, "policy")
	entries, err := os.ReadDir(policyDir)
	if err != nil {
		if os.IsNotExist(err) {
			return []PolicyFileInfo{}, nil
		}
		return nil, fmt.Errorf("failed to read policy directory: %w", err)
	}

	var policies []PolicyFileInfo
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".yaml") {
			continue
		}

		// Parse the file to get name and type
		filePath := filepath.Join(policyDir, entry.Name())
		content, err := os.ReadFile(filePath)
		if err != nil {
			continue
		}

		var policyData struct {
			Name string `yaml:"name"`
			Type string `yaml:"type"`
		}
		if err := yaml.Unmarshal(content, &policyData); err != nil {
			continue
		}

		policies = append(policies, PolicyFileInfo{
			Filename: entry.Name(),
			Name:     policyData.Name,
			Type:     policyData.Type,
		})
	}

	return policies, nil
}

// validateFilename checks that a filename is non-empty and doesn't contain
// path-traversal characters that could escape the target directory.
func validateFilename(filename string) error {
	if filename == "" {
		return fmt.Errorf("filename is required")
	}
	if strings.Contains(filename, "..") || strings.Contains(filename, "/") || strings.Contains(filename, "\\") {
		return fmt.Errorf("invalid filename")
	}
	return nil
}

// GetPolicyFileYaml returns the raw YAML content of a single policy file.
func (a *App) GetPolicyFileYaml(slug, filename string) (string, error) {
	config, err := a.getConfig()
	if err != nil {
		return "", err
	}

	if err := validateFilename(filename); err != nil {
		return "", err
	}

	policyPath := filepath.Join(config.EndpointsPath, slug, "policy", filename)
	content, err := os.ReadFile(policyPath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", fmt.Errorf("policy file not found: %s", filename)
		}
		return "", fmt.Errorf("failed to read policy file: %w", err)
	}

	return string(content), nil
}

// SavePolicyFileYaml saves raw YAML content to a policy file.
func (a *App) SavePolicyFileYaml(slug, filename, content string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	if err := validateFilename(filename); err != nil {
		return err
	}

	// Validate YAML syntax before saving
	if err := validateYAML(content); err != nil {
		return err
	}

	policyDir := filepath.Join(config.EndpointsPath, slug, "policy")

	// Create policy directory if it doesn't exist
	if err := os.MkdirAll(policyDir, 0755); err != nil {
		return fmt.Errorf("failed to create policy directory: %w", err)
	}

	policyPath := filepath.Join(policyDir, filename)
	if err := os.WriteFile(policyPath, []byte(content), 0644); err != nil {
		return fmt.Errorf("failed to write policy file: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Saved policy file '%s' for endpoint: %s", filename, slug))
	return nil
}

// DeletePolicyFile removes a policy file from the endpoint's policy/ directory.
func (a *App) DeletePolicyFile(slug, filename string) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	if err := validateFilename(filename); err != nil {
		return err
	}

	policyPath := filepath.Join(config.EndpointsPath, slug, "policy", filename)
	if err := os.Remove(policyPath); err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("policy file not found: %s", filename)
		}
		return fmt.Errorf("failed to delete policy file: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Deleted policy file '%s' from endpoint: %s", filename, slug))
	return nil
}

// policyDef is the top-level structure serialized to YAML for a policy file.
type policyDef struct {
	Type   string      `yaml:"type"`
	Name   string      `yaml:"name"`
	Config interface{} `yaml:"config,omitempty"`
}

// marshalPolicyYAML marshals a policyDef to YAML with an optional comment header.
func marshalPolicyYAML(comment string, def policyDef) string {
	out, err := yaml.Marshal(&def)
	if err != nil {
		// Fallback: should never happen with known struct types.
		return fmt.Sprintf("type: %s\nname: %s\nconfig: {}\n", def.Type, def.Name)
	}
	if comment != "" {
		return comment + string(out)
	}
	return string(out)
}

// generatePolicyYAML generates YAML content for a policy based on its type.
// Uses yaml.Marshal to ensure proper escaping of user-supplied values.
func generatePolicyYAML(req NewPolicyRequest) string {
	switch req.Type {
	case "AccessGroupPolicy":
		type accessGroupConfig struct {
			Users []string `yaml:"users"`
		}
		return marshalPolicyYAML(
			"# Access Group Policy\n# Controls access based on user group membership\n",
			policyDef{Type: "AccessGroupPolicy", Name: req.Name, Config: accessGroupConfig{
				Users: []string{"user@example.com"},
			}},
		)

	case "RateLimitPolicy":
		type rateLimitConfig struct {
			MaxRequests   int `yaml:"max_requests"`
			WindowSeconds int `yaml:"window_seconds"`
		}
		return marshalPolicyYAML(
			"# Rate Limit Policy\n# Limits the number of requests per time window\n",
			policyDef{Type: "RateLimitPolicy", Name: req.Name, Config: rateLimitConfig{
				MaxRequests: 100, WindowSeconds: 3600,
			}},
		)

	case "TokenLimitPolicy":
		type tokenLimitConfig struct {
			MaxTokensPerRequest int `yaml:"max_tokens_per_request"`
			MaxTokensPerWindow  int `yaml:"max_tokens_per_window"`
			WindowSeconds       int `yaml:"window_seconds"`
		}
		return marshalPolicyYAML(
			"# Token Limit Policy\n# Limits token usage for LLM endpoints\n",
			policyDef{Type: "TokenLimitPolicy", Name: req.Name, Config: tokenLimitConfig{
				MaxTokensPerRequest: 4096, MaxTokensPerWindow: 100000, WindowSeconds: 3600,
			}},
		)

	case "PromptFilterPolicy":
		type promptFilterConfig struct {
			Patterns []string `yaml:"patterns"`
		}
		return marshalPolicyYAML(
			"# Prompt Filter Policy\n# Filters requests based on prompt content patterns\n",
			policyDef{Type: "PromptFilterPolicy", Name: req.Name, Config: promptFilterConfig{
				Patterns: []string{"(?i)password", "(?i)secret", "(?i)api.?key"},
			}},
		)

	case "AttributionPolicy":
		type attributionConfig struct {
			TrackFields []string `yaml:"track_fields"`
			LogPath     string   `yaml:"log_path"`
		}
		return marshalPolicyYAML(
			"# Attribution Policy\n# Tracks data usage attribution for audit purposes\n",
			policyDef{Type: "AttributionPolicy", Name: req.Name, Config: attributionConfig{
				TrackFields: []string{"user_id", "endpoint_slug", "timestamp"},
				LogPath:     ".attribution_log.jsonl",
			}},
		)

	case "ManualReviewPolicy":
		type manualReviewConfig struct {
			TimeoutSeconds int    `yaml:"timeout_seconds"`
			WebhookURL     string `yaml:"webhook_url"`
		}
		return marshalPolicyYAML(
			"# Manual Review Policy\n# Requires manual approval for requests\n",
			policyDef{Type: "ManualReviewPolicy", Name: req.Name, Config: manualReviewConfig{
				TimeoutSeconds: 3600, WebhookURL: "",
			}},
		)

	case "TransactionPolicy":
		type transactionConfig struct {
			CostPerRequest int `yaml:"cost_per_request"`
			InitialBalance int `yaml:"initial_balance"`
		}
		return marshalPolicyYAML(
			"# Transaction Policy\n# Manages credit/token-based transactions\n",
			policyDef{Type: "TransactionPolicy", Name: req.Name, Config: transactionConfig{
				CostPerRequest: 1, InitialBalance: 100,
			}},
		)

	case "BundleSubscriptionPolicy":
		type bundleConfig struct {
			PlanName     string  `yaml:"plan_name"`
			Price        float64 `yaml:"price"`
			Currency     string  `yaml:"currency"`
			BillingCycle string  `yaml:"billing_cycle"`
			InvoiceURL   string  `yaml:"invoice_url"`
		}
		return marshalPolicyYAML(
			"# Bundle Subscription Policy\n# Gates access behind an active subscription plan\n",
			policyDef{Type: "bundle_subscription", Name: req.Name, Config: bundleConfig{
				PlanName: "Pro", Price: 29.99, Currency: "USD",
				BillingCycle: "monthly", InvoiceURL: "",
			}},
		)

	case "AllOfPolicy":
		type allOfConfig struct {
			Policies []string `yaml:"policies"`
		}
		children := req.ChildPolicies
		if len(children) == 0 {
			children = []string{"policy_name_1", "policy_name_2"}
		}
		return marshalPolicyYAML(
			"# All-Of Policy (Composite)\n# ALL child policies must pass for the request to be allowed\n",
			policyDef{Type: "AllOfPolicy", Name: req.Name, Config: allOfConfig{Policies: children}},
		)

	case "AnyOfPolicy":
		type anyOfConfig struct {
			Policies []string `yaml:"policies"`
		}
		children := req.ChildPolicies
		if len(children) == 0 {
			children = []string{"policy_name_1", "policy_name_2"}
		}
		return marshalPolicyYAML(
			"# Any-Of Policy (Composite)\n# At least ONE child policy must pass for the request to be allowed\n",
			policyDef{Type: "AnyOfPolicy", Name: req.Name, Config: anyOfConfig{Policies: children}},
		)

	case "NotPolicy":
		type notConfig struct {
			Policy     string `yaml:"policy"`
			DenyReason string `yaml:"deny_reason"`
		}
		childPolicyName := "policy_to_negate"
		if len(req.ChildPolicies) > 0 {
			childPolicyName = req.ChildPolicies[0]
		}
		denyReason := req.DenyReason
		if denyReason == "" {
			denyReason = "Access denied by policy negation"
		}
		return marshalPolicyYAML(
			"# Not Policy (Composite)\n# Inverts the result of the wrapped policy\n",
			policyDef{Type: "NotPolicy", Name: req.Name, Config: notConfig{
				Policy: childPolicyName, DenyReason: denyReason,
			}},
		)

	default:
		return marshalPolicyYAML(
			"# Policy configuration\n",
			policyDef{Type: req.Type, Name: req.Name, Config: map[string]any{}},
		)
	}
}

// CreatePolicyFile creates a new policy file with a template based on the request.
func (a *App) CreatePolicyFile(slug string, req NewPolicyRequest) error {
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	if req.Name == "" {
		return fmt.Errorf("policy name is required")
	}

	if req.Type == "" {
		return fmt.Errorf("policy type is required")
	}

	// Generate filename from policy name
	filename := nodeops.SlugifyFilename(req.Name)

	policyDir := filepath.Join(config.EndpointsPath, slug, "policy")

	// Create policy directory if it doesn't exist
	if err := os.MkdirAll(policyDir, 0755); err != nil {
		return fmt.Errorf("failed to create policy directory: %w", err)
	}

	policyPath := filepath.Join(policyDir, filename)

	// Check if file already exists
	if _, err := os.Stat(policyPath); err == nil {
		return fmt.Errorf("policy file already exists: %s", filename)
	}

	// Generate template content based on policy type
	content := generatePolicyYAML(req)

	if err := os.WriteFile(policyPath, []byte(content), 0644); err != nil {
		return fmt.Errorf("failed to create policy file: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Created policy file '%s' (type: %s) for endpoint: %s", filename, req.Type, slug))
	return nil
}

// ============================================================================
// Endpoint Creation
// ============================================================================

// CreateEndpointRequest contains the parameters for creating a new endpoint.
type CreateEndpointRequest struct {
	Name        string `json:"name"`        // Display name (required)
	Type        string `json:"type"`        // "model" or "data_source" (required)
	Description string `json:"description"` // Optional description
	Version     string `json:"version"`     // Optional, defaults to "1.0.0"
}

// CheckEndpointExists checks if an endpoint with the given name already exists.
// Returns the generated slug and whether it exists.
func (a *App) CheckEndpointExists(name string) (string, bool) {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.config == nil {
		return "", false
	}

	slug := nodeops.Slugify(name)
	if slug == "" {
		return "", false
	}

	endpointDir := filepath.Join(a.config.EndpointsPath, slug)
	_, err := os.Stat(endpointDir)
	exists := !os.IsNotExist(err)

	return slug, exists
}

// DeleteEndpoint deletes an endpoint and all its associated files.
// This includes the endpoint folder, virtual environments, and all configuration files.
func (a *App) DeleteEndpoint(slug string) error {
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.config == nil {
		return fmt.Errorf("app not configured")
	}

	mgr := nodeops.NewManager(a.config.EndpointsPath)
	if err := mgr.DeleteEndpoint(slug); err != nil {
		return err
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Deleted endpoint: %s", slug))
	// Don't emit app:endpoints-changed here — the file watcher will detect
	// the deletion and emit the correct endpoint list after reloading.
	// Emitting nil here caused a race where the frontend's optimistic delete
	// was overwritten before the file watcher could confirm it.
	return nil
}

// CreateEndpoint creates a new endpoint with the given configuration.
// Returns the slug of the created endpoint.
func (a *App) CreateEndpoint(req CreateEndpointRequest) (string, error) {
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.config == nil {
		return "", fmt.Errorf("app not configured")
	}

	// Validate required fields
	if req.Name == "" {
		return "", fmt.Errorf("endpoint name is required")
	}
	if !syfthubapi.IsValidEndpointType(req.Type) {
		return "", fmt.Errorf("endpoint type must be one of: %v", syfthubapi.ValidEndpointTypes)
	}

	// Generate slug from name
	slug := nodeops.Slugify(req.Name)
	if slug == "" {
		return "", fmt.Errorf("could not generate valid slug from name '%s'", req.Name)
	}

	// Check if endpoint already exists
	endpointDir := filepath.Join(a.config.EndpointsPath, slug)
	if _, err := os.Stat(endpointDir); !os.IsNotExist(err) {
		return "", fmt.Errorf("endpoint '%s' already exists", slug)
	}

	// Set defaults
	version := req.Version
	if version == "" {
		version = "1.0.0"
	}

	// Create endpoint directory
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create endpoint directory: %w", err)
	}

	// Helper to clean up on failure
	cleanup := func() {
		os.RemoveAll(endpointDir)
	}

	// Create runner.py with appropriate handler function
	runnerContent := nodeops.GetRunnerTemplate(req.Type)
	runnerPath := filepath.Join(endpointDir, "runner.py")
	if err := os.WriteFile(runnerPath, []byte(runnerContent), 0644); err != nil {
		cleanup()
		return "", fmt.Errorf("failed to create runner.py: %w", err)
	}

	// Create pyproject.toml with basic structure
	pyprojectContent := fmt.Sprintf(`[project]
name = "%s"
version = "%s"
dependencies = []
`, slug, version)

	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	if err := os.WriteFile(pyprojectPath, []byte(pyprojectContent), 0644); err != nil {
		cleanup()
		return "", fmt.Errorf("failed to create pyproject.toml: %w", err)
	}

	// Create README.md with YAML frontmatter (required by the SDK)
	description := req.Description
	if description == "" {
		description = fmt.Sprintf("A %s endpoint created with SyftHub Desktop", req.Type)
	}
	readmeContent := fmt.Sprintf(`---
slug: %s
type: %s
name: %s
description: %s
enabled: true
version: "%s"
env:
  required: []
  optional: []
  inherit: [PATH, HOME]
runtime:
  workers: 1
  timeout: 30
---

# %s

%s

## Usage

This endpoint was created using SyftHub Desktop.

Edit the runner.py file to implement your endpoint logic.
`, slug, req.Type, req.Name, description, version, req.Name, description)

	readmePath := filepath.Join(endpointDir, "README.md")
	runtime.LogInfo(a.ctx, fmt.Sprintf("Writing README.md with content starting: %q", readmeContent[:min(100, len(readmeContent))]))
	if err := os.WriteFile(readmePath, []byte(readmeContent), 0644); err != nil {
		cleanup()
		return "", fmt.Errorf("failed to create README.md: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Created endpoint '%s' (type: %s)", slug, req.Type))

	// Notify frontend about new endpoint
	runtime.EventsEmit(a.ctx, "app:endpoints-changed", nil)

	return slug, nil
}
