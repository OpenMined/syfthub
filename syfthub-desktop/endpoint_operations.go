// Package main provides endpoint file operations for the SyftHub Desktop GUI.
// These methods enable reading and writing endpoint files (runner.py, README.md, .env, etc.)
package main

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	goruntime "runtime"
	"strings"

	"github.com/wailsapp/wails/v2/pkg/runtime"
	"gopkg.in/yaml.v3"
)

// EndpointDetail provides full endpoint information for the detail view.
type EndpointDetail struct {
	Slug            string   `json:"slug"`
	Name            string   `json:"name"`
	Description     string   `json:"description"`
	Type            string   `json:"type"`
	Version         string   `json:"version"`
	Enabled         bool     `json:"enabled"`
	HasReadme       bool     `json:"hasReadme"`
	HasPolicies     bool     `json:"hasPolicies"`
	DepsCount       int      `json:"depsCount"`
	EnvCount        int      `json:"envCount"`
	RunnerCode      string   `json:"runnerCode"`
	ReadmeContent   string   `json:"readmeContent"`
	Policies        []Policy `json:"policies"`
	PoliciesVersion string   `json:"policiesVersion"`
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

// Policy represents a single policy from policies.yaml.
type Policy struct {
	Name   string                 `json:"name" yaml:"name"`
	Type   string                 `json:"type" yaml:"type"`
	Config map[string]interface{} `json:"config" yaml:"config"`
}

// PoliciesFile represents the full policies.yaml structure.
type PoliciesFile struct {
	Version  string                 `yaml:"version"`
	Store    map[string]interface{} `yaml:"store"`
	Policies []Policy               `yaml:"policies"`
}

// OverviewData contains endpoint overview fields for update.
type OverviewData struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Type        string `json:"type"`
	Version     string `json:"version"`
}

// GetEndpointDetail returns full details for an endpoint.
func (a *App) GetEndpointDetail(slug string) (*EndpointDetail, error) {
	a.mu.RLock()
	defer a.mu.RUnlock()

	runtime.LogInfo(a.ctx, fmt.Sprintf("GetEndpointDetail called for slug: %s", slug))

	if a.config == nil {
		runtime.LogError(a.ctx, "GetEndpointDetail: app not configured")
		return nil, fmt.Errorf("app not configured")
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("GetEndpointDetail: endpoints path = %s", a.config.EndpointsPath))

	endpointDir := filepath.Join(a.config.EndpointsPath, slug)
	runtime.LogInfo(a.ctx, fmt.Sprintf("GetEndpointDetail: looking for endpoint at %s", endpointDir))

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
	if _, err := os.Stat(readmePath); err == nil {
		detail.HasReadme = true
		if content, err := os.ReadFile(readmePath); err == nil {
			detail.ReadmeContent = string(content)
		}

		// Parse frontmatter for metadata
		if frontmatter, _, err := a.parseReadmeFrontmatter(readmePath); err == nil {
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

	// Check for policies.yaml file and parse it
	policiesPath := filepath.Join(endpointDir, "policies.yaml")
	if policies, version, err := a.parsePoliciesYaml(policiesPath); err == nil {
		detail.HasPolicies = true
		detail.Policies = policies
		detail.PoliciesVersion = version
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

	runtime.LogInfo(a.ctx, fmt.Sprintf("GetEndpointDetail: returning detail for %s (name=%s, type=%s, enabled=%v, hasRunner=%v, hasReadme=%v)",
		slug, detail.Name, detail.Type, detail.Enabled, len(detail.RunnerCode) > 0, detail.HasReadme))

	return detail, nil
}

// ReadmeFrontmatter represents the YAML frontmatter in README.md
type ReadmeFrontmatter struct {
	Slug        string `yaml:"slug"`
	Name        string `yaml:"name"`
	Description string `yaml:"description"`
	Type        string `yaml:"type"`
	Version     string `yaml:"version"`
	Enabled     *bool  `yaml:"enabled"`
}

// parseReadmeFrontmatter parses YAML frontmatter from README.md into EndpointDetail.
// Returns (frontmatter, body, error) where body is the markdown content after frontmatter.
func (a *App) parseReadmeFrontmatter(path string) (*ReadmeFrontmatter, string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, "", err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)

	// Look for opening ---
	if !scanner.Scan() {
		return nil, "", fmt.Errorf("empty file")
	}

	firstLine := strings.TrimSpace(scanner.Text())
	if firstLine != "---" {
		return nil, "", fmt.Errorf("missing YAML frontmatter (expected '---')")
	}

	// Collect YAML content
	var yamlLines []string
	foundClose := false

	for scanner.Scan() {
		line := scanner.Text()
		if strings.TrimSpace(line) == "---" {
			foundClose = true
			break
		}
		yamlLines = append(yamlLines, line)
	}

	if err := scanner.Err(); err != nil {
		return nil, "", fmt.Errorf("error reading file: %w", err)
	}

	if !foundClose {
		return nil, "", fmt.Errorf("unclosed YAML frontmatter (missing closing '---')")
	}

	// Collect body content (everything after frontmatter)
	var bodyLines []string
	for scanner.Scan() {
		bodyLines = append(bodyLines, scanner.Text())
	}

	if err := scanner.Err(); err != nil {
		return nil, "", fmt.Errorf("error reading file body: %w", err)
	}

	// Parse YAML
	yamlContent := strings.Join(yamlLines, "\n")
	var frontmatter ReadmeFrontmatter
	if err := yaml.Unmarshal([]byte(yamlContent), &frontmatter); err != nil {
		return nil, "", fmt.Errorf("invalid YAML frontmatter: %w", err)
	}

	body := strings.TrimSpace(strings.Join(bodyLines, "\n"))

	return &frontmatter, body, nil
}

// updateReadmeFrontmatter updates specific fields in the README.md frontmatter while preserving the body.
func (a *App) updateReadmeFrontmatter(path string, updates map[string]interface{}) error {
	// Read the entire file
	content, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	lines := strings.Split(string(content), "\n")

	// Find frontmatter boundaries
	if len(lines) == 0 || strings.TrimSpace(lines[0]) != "---" {
		return fmt.Errorf("file does not have YAML frontmatter")
	}

	frontmatterEnd := -1
	for i := 1; i < len(lines); i++ {
		if strings.TrimSpace(lines[i]) == "---" {
			frontmatterEnd = i
			break
		}
	}

	if frontmatterEnd == -1 {
		return fmt.Errorf("unclosed YAML frontmatter")
	}

	// Parse existing frontmatter
	yamlContent := strings.Join(lines[1:frontmatterEnd], "\n")
	var frontmatter map[string]interface{}
	if err := yaml.Unmarshal([]byte(yamlContent), &frontmatter); err != nil {
		return fmt.Errorf("failed to parse frontmatter: %w", err)
	}

	// Apply updates
	for key, value := range updates {
		frontmatter[key] = value
	}

	// Serialize updated frontmatter
	newYaml, err := yaml.Marshal(frontmatter)
	if err != nil {
		return fmt.Errorf("failed to serialize frontmatter: %w", err)
	}

	// Reconstruct file
	var result strings.Builder
	result.WriteString("---\n")
	result.Write(newYaml)
	result.WriteString("---\n")

	// Add body (everything after frontmatter)
	if frontmatterEnd+1 < len(lines) {
		result.WriteString(strings.Join(lines[frontmatterEnd+1:], "\n"))
	}

	return os.WriteFile(path, []byte(result.String()), 0644)
}

// parsePoliciesYaml parses policies.yaml and returns the policies list.
func (a *App) parsePoliciesYaml(path string) ([]Policy, string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, "", err
	}

	var pf PoliciesFile
	if err := yaml.Unmarshal(content, &pf); err != nil {
		return nil, "", fmt.Errorf("failed to parse policies.yaml: %w", err)
	}

	return pf.Policies, pf.Version, nil
}

// GetRunnerCode returns the runner.py content for an endpoint.
func (a *App) GetRunnerCode(slug string) (string, error) {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.config == nil {
		return "", fmt.Errorf("app not configured")
	}

	runnerPath := filepath.Join(a.config.EndpointsPath, slug, "runner.py")
	content, err := os.ReadFile(runnerPath)
	if err != nil {
		return "", fmt.Errorf("failed to read runner.py: %w", err)
	}

	return string(content), nil
}

// SaveRunnerCode saves the runner.py content for an endpoint.
func (a *App) SaveRunnerCode(slug, code string) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
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
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.config == nil {
		return "", fmt.Errorf("app not configured")
	}

	readmePath := filepath.Join(a.config.EndpointsPath, slug, "README.md")
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
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
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
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.config == nil {
		return nil, fmt.Errorf("app not configured")
	}

	envPath := filepath.Join(a.config.EndpointsPath, slug, ".env")
	return a.readEnvFile(envPath)
}

// readEnvFile reads a .env file and returns key-value pairs.
func (a *App) readEnvFile(path string) ([]EnvVar, error) {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return []EnvVar{}, nil
		}
		return nil, err
	}
	defer file.Close()

	var vars []EnvVar
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		// Parse KEY=value
		parts := strings.SplitN(line, "=", 2)
		if len(parts) == 2 {
			key := strings.TrimSpace(parts[0])
			value := strings.TrimSpace(parts[1])
			// Remove quotes if present
			value = strings.Trim(value, "\"'")
			vars = append(vars, EnvVar{Key: key, Value: value})
		}
	}

	return vars, scanner.Err()
}

// SetEnvironment adds or updates an environment variable.
func (a *App) SetEnvironment(slug, key, value string) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
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
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
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
	var lines []string
	for _, v := range vars {
		// Quote values containing spaces or special characters
		value := v.Value
		if strings.ContainsAny(value, " \t\n\"'") {
			value = fmt.Sprintf("\"%s\"", strings.ReplaceAll(value, "\"", "\\\""))
		}
		lines = append(lines, fmt.Sprintf("%s=%s", v.Key, value))
	}

	content := strings.Join(lines, "\n")
	if len(lines) > 0 {
		content += "\n"
	}

	return os.WriteFile(path, []byte(content), 0644)
}

// GetDependencies returns Python dependencies for an endpoint.
func (a *App) GetDependencies(slug string) ([]Dependency, error) {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.config == nil {
		return nil, fmt.Errorf("app not configured")
	}

	pyprojectPath := filepath.Join(a.config.EndpointsPath, slug, "pyproject.toml")
	return a.readDependencies(pyprojectPath)
}

// readDependencies reads dependencies from pyproject.toml.
func (a *App) readDependencies(path string) ([]Dependency, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return []Dependency{}, nil
		}
		return nil, err
	}

	var deps []Dependency
	lines := strings.Split(string(content), "\n")
	inDeps := false

	// Simple regex for dependency format: "package>=version" or "package==version"
	depRegex := regexp.MustCompile(`^["']?([a-zA-Z0-9_-]+)([><=!~]+)?([0-9.]+)?["']?,?$`)

	for _, line := range lines {
		line = strings.TrimSpace(line)

		// Check for dependencies section
		if line == "[project.dependencies]" || strings.HasPrefix(line, "dependencies = [") {
			inDeps = true
			continue
		}

		// End of dependencies section
		if inDeps && (strings.HasPrefix(line, "[") || line == "]") {
			if line == "]" {
				continue
			}
			inDeps = false
			continue
		}

		if inDeps && line != "" && !strings.HasPrefix(line, "#") {
			// Parse dependency line
			match := depRegex.FindStringSubmatch(line)
			if len(match) >= 2 {
				pkg := match[1]
				version := ""
				if len(match) >= 4 && match[3] != "" {
					version = match[3]
				}
				deps = append(deps, Dependency{Package: pkg, Version: version})
			}
		}
	}

	return deps, nil
}

// AddDependency adds a dependency to the endpoint's pyproject.toml.
func (a *App) AddDependency(slug, pkg, version string) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	if pkg == "" {
		return fmt.Errorf("package name is required")
	}

	pyprojectPath := filepath.Join(config.EndpointsPath, slug, "pyproject.toml")

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

	for i, line := range lines {
		trimmed := strings.TrimSpace(line)

		// Found dependencies array start
		if strings.HasPrefix(trimmed, "dependencies = [") {
			foundDeps = true
			newLines = append(newLines, line)

			// Check if it's a single-line empty array
			if trimmed == "dependencies = []" {
				newLines[len(newLines)-1] = "dependencies = ["
				newLines = append(newLines, fmt.Sprintf("    \"%s\",", depStr))
				newLines = append(newLines, "]")
				addedDep = true
				continue
			}
			continue
		}

		// Inside dependencies array, looking for closing bracket
		if foundDeps && !addedDep {
			if trimmed == "]" {
				// Add new dependency before closing bracket
				newLines = append(newLines, fmt.Sprintf("    \"%s\",", depStr))
				addedDep = true
			}
		}

		newLines = append(newLines, line)

		// Handle [project.dependencies] section format
		if trimmed == "[project.dependencies]" {
			foundDeps = true
			// Find end of section or file and add dependency
			for j := i + 1; j < len(lines); j++ {
				nextTrimmed := strings.TrimSpace(lines[j])
				if strings.HasPrefix(nextTrimmed, "[") || j == len(lines)-1 {
					// Insert before next section
					break
				}
			}
		}
	}

	// If no dependencies section found, create one
	if !foundDeps {
		// Check if [project] section exists
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
			// Add after [project] section
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
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
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
		if strings.HasPrefix(trimmed, "dependencies = [") || trimmed == "[project.dependencies]" {
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
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	readmePath := filepath.Join(config.EndpointsPath, slug, "README.md")

	// Update README.md frontmatter
	updates := map[string]interface{}{
		"name":        name,
		"description": description,
		"type":        endpointType,
		"version":     version,
	}

	if err := a.updateReadmeFrontmatter(readmePath, updates); err != nil {
		return fmt.Errorf("failed to update README.md frontmatter: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Updated endpoint overview: %s", slug))
	return nil
}

// ToggleEndpointEnabled toggles the enabled status of an endpoint.
// This uses a fast path that updates the registry directly without recreating executors.
func (a *App) ToggleEndpointEnabled(slug string) (bool, error) {
	a.mu.RLock()
	config := a.config
	core := a.core
	a.mu.RUnlock()

	if config == nil {
		return false, fmt.Errorf("app not configured")
	}

	readmePath := filepath.Join(config.EndpointsPath, slug, "README.md")

	// Read current state from README.md frontmatter
	frontmatter, _, err := a.parseReadmeFrontmatter(readmePath)
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
	if err := a.updateReadmeFrontmatter(readmePath, updates); err != nil {
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

// OpenEndpointsFolder opens the endpoints directory in the system file explorer.
func (a *App) OpenEndpointsFolder() error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	// Check if the directory exists
	if _, err := os.Stat(config.EndpointsPath); os.IsNotExist(err) {
		return fmt.Errorf("endpoints folder does not exist: %s", config.EndpointsPath)
	}

	// Use platform-specific commands to open the folder
	var cmd *exec.Cmd
	switch goruntime.GOOS {
	case "windows":
		cmd = exec.Command("explorer", config.EndpointsPath)
	case "darwin":
		cmd = exec.Command("open", config.EndpointsPath)
	default: // Linux and others
		cmd = exec.Command("xdg-open", config.EndpointsPath)
	}

	return cmd.Start()
}

// OpenEndpointFolder opens a specific endpoint directory in the file explorer.
func (a *App) OpenEndpointFolder(slug string) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	endpointPath := filepath.Join(config.EndpointsPath, slug)

	// Check if the directory exists
	if _, err := os.Stat(endpointPath); os.IsNotExist(err) {
		return fmt.Errorf("endpoint folder does not exist: %s", endpointPath)
	}

	// Use platform-specific commands to open the folder
	var cmd *exec.Cmd
	switch goruntime.GOOS {
	case "windows":
		cmd = exec.Command("explorer", endpointPath)
	case "darwin":
		cmd = exec.Command("open", endpointPath)
	default: // Linux and others
		cmd = exec.Command("xdg-open", endpointPath)
	}

	return cmd.Start()
}

// SavePolicy creates or updates a policy in the endpoint's policies.yaml.
// If a policy with the same name exists, it will be updated; otherwise, a new one is created.
func (a *App) SavePolicy(slug string, policy Policy) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	if policy.Name == "" {
		return fmt.Errorf("policy name is required")
	}

	if policy.Type == "" {
		return fmt.Errorf("policy type is required")
	}

	policiesPath := filepath.Join(config.EndpointsPath, slug, "policies.yaml")

	// Read existing policies file or create new structure
	var pf PoliciesFile
	if content, err := os.ReadFile(policiesPath); err == nil {
		if err := yaml.Unmarshal(content, &pf); err != nil {
			return fmt.Errorf("failed to parse policies.yaml: %w", err)
		}
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("failed to read policies.yaml: %w", err)
	} else {
		// File doesn't exist, create default structure
		pf = PoliciesFile{
			Version: "1.0",
			Store: map[string]interface{}{
				"type": "sqlite",
				"path": ".policy_store.db",
			},
			Policies: []Policy{},
		}
	}

	// Find and update existing policy, or append new one
	found := false
	for i, p := range pf.Policies {
		if p.Name == policy.Name {
			pf.Policies[i] = policy
			found = true
			break
		}
	}
	if !found {
		pf.Policies = append(pf.Policies, policy)
	}

	// Marshal and write back
	content, err := yaml.Marshal(&pf)
	if err != nil {
		return fmt.Errorf("failed to marshal policies: %w", err)
	}

	if err := os.WriteFile(policiesPath, content, 0644); err != nil {
		return fmt.Errorf("failed to write policies.yaml: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Saved policy '%s' for endpoint: %s", policy.Name, slug))
	return nil
}

// DeletePolicy removes a policy from the endpoint's policies.yaml by name.
func (a *App) DeletePolicy(slug, policyName string) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	if policyName == "" {
		return fmt.Errorf("policy name is required")
	}

	policiesPath := filepath.Join(config.EndpointsPath, slug, "policies.yaml")

	// Read existing policies file
	content, err := os.ReadFile(policiesPath)
	if err != nil {
		return fmt.Errorf("failed to read policies.yaml: %w", err)
	}

	var pf PoliciesFile
	if err := yaml.Unmarshal(content, &pf); err != nil {
		return fmt.Errorf("failed to parse policies.yaml: %w", err)
	}

	// Find and remove the policy
	found := false
	var newPolicies []Policy
	for _, p := range pf.Policies {
		if p.Name == policyName {
			found = true
			continue
		}
		newPolicies = append(newPolicies, p)
	}

	if !found {
		return fmt.Errorf("policy not found: %s", policyName)
	}

	pf.Policies = newPolicies

	// Marshal and write back
	newContent, err := yaml.Marshal(&pf)
	if err != nil {
		return fmt.Errorf("failed to marshal policies: %w", err)
	}

	if err := os.WriteFile(policiesPath, newContent, 0644); err != nil {
		return fmt.Errorf("failed to write policies.yaml: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Deleted policy '%s' from endpoint: %s", policyName, slug))
	return nil
}

// GetPolicies returns the policies for an endpoint.
func (a *App) GetPolicies(slug string) ([]Policy, error) {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return nil, fmt.Errorf("app not configured")
	}

	policiesPath := filepath.Join(config.EndpointsPath, slug, "policies.yaml")
	policies, _, err := a.parsePoliciesYaml(policiesPath)
	if err != nil {
		if os.IsNotExist(err) {
			return []Policy{}, nil
		}
		return nil, err
	}

	return policies, nil
}

// GetPoliciesYaml returns the raw policies.yaml content for an endpoint.
func (a *App) GetPoliciesYaml(slug string) (string, error) {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return "", fmt.Errorf("app not configured")
	}

	policiesPath := filepath.Join(config.EndpointsPath, slug, "policies.yaml")
	content, err := os.ReadFile(policiesPath)
	if err != nil {
		if os.IsNotExist(err) {
			// Return default template if file doesn't exist
			return `# Policy configuration
version: "1.0"

# Store configuration for stateful policies
store:
  type: sqlite
  path: .policy_store.db

# Policies are evaluated in order
policies: []
`, nil
		}
		return "", fmt.Errorf("failed to read policies.yaml: %w", err)
	}

	return string(content), nil
}

// SavePoliciesYaml saves raw YAML content to the endpoint's policies.yaml file.
func (a *App) SavePoliciesYaml(slug, content string) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	// Validate YAML syntax before saving
	var test interface{}
	if err := yaml.Unmarshal([]byte(content), &test); err != nil {
		return fmt.Errorf("invalid YAML syntax: %w", err)
	}

	policiesPath := filepath.Join(config.EndpointsPath, slug, "policies.yaml")
	if err := os.WriteFile(policiesPath, []byte(content), 0644); err != nil {
		return fmt.Errorf("failed to write policies.yaml: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Saved policies.yaml for endpoint: %s", slug))
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
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return nil, fmt.Errorf("app not configured")
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

// GetPolicyFileYaml returns the raw YAML content of a single policy file.
func (a *App) GetPolicyFileYaml(slug, filename string) (string, error) {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return "", fmt.Errorf("app not configured")
	}

	if filename == "" {
		return "", fmt.Errorf("filename is required")
	}

	// Security: ensure filename doesn't escape the policy directory
	if strings.Contains(filename, "..") || strings.Contains(filename, "/") || strings.Contains(filename, "\\") {
		return "", fmt.Errorf("invalid filename")
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
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	if filename == "" {
		return fmt.Errorf("filename is required")
	}

	// Security: ensure filename doesn't escape the policy directory
	if strings.Contains(filename, "..") || strings.Contains(filename, "/") || strings.Contains(filename, "\\") {
		return fmt.Errorf("invalid filename")
	}

	// Validate YAML syntax before saving
	var test interface{}
	if err := yaml.Unmarshal([]byte(content), &test); err != nil {
		return fmt.Errorf("invalid YAML syntax: %w", err)
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
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	if filename == "" {
		return fmt.Errorf("filename is required")
	}

	// Security: ensure filename doesn't escape the policy directory
	if strings.Contains(filename, "..") || strings.Contains(filename, "/") || strings.Contains(filename, "\\") {
		return fmt.Errorf("invalid filename")
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

// slugifyFilename converts a policy name to a valid filename.
// E.g., "My Rate Limit Policy" -> "my-rate-limit-policy.yaml"
func slugifyFilename(name string) string {
	// Convert to lowercase
	slug := strings.ToLower(name)
	// Replace spaces and underscores with hyphens
	slug = strings.ReplaceAll(slug, " ", "-")
	slug = strings.ReplaceAll(slug, "_", "-")
	// Remove any characters that aren't alphanumeric or hyphens
	var result strings.Builder
	for _, r := range slug {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' {
			result.WriteRune(r)
		}
	}
	slug = result.String()
	// Remove consecutive hyphens
	for strings.Contains(slug, "--") {
		slug = strings.ReplaceAll(slug, "--", "-")
	}
	// Trim leading/trailing hyphens
	slug = strings.Trim(slug, "-")
	// Default if empty
	if slug == "" {
		slug = "new-policy"
	}
	return slug + ".yaml"
}

// generatePolicyYAML generates YAML content for a policy based on its type.
func generatePolicyYAML(req NewPolicyRequest) string {
	switch req.Type {
	case "AccessGroupPolicy":
		return fmt.Sprintf(`# Access Group Policy
# Controls access based on user group membership
type: AccessGroupPolicy
name: %s
config:
  # List of user IDs or emails that can access this endpoint
  users:
    - user@example.com
`, req.Name)

	case "RateLimitPolicy":
		return fmt.Sprintf(`# Rate Limit Policy
# Limits the number of requests per time window
type: RateLimitPolicy
name: %s
config:
  # Maximum number of requests allowed in the window
  max_requests: 100
  # Time window in seconds
  window_seconds: 3600
`, req.Name)

	case "TokenLimitPolicy":
		return fmt.Sprintf(`# Token Limit Policy
# Limits token usage for LLM endpoints
type: TokenLimitPolicy
name: %s
config:
  # Maximum tokens per request
  max_tokens_per_request: 4096
  # Maximum tokens per time window (optional)
  max_tokens_per_window: 100000
  # Time window in seconds for window-based limiting
  window_seconds: 3600
`, req.Name)

	case "PromptFilterPolicy":
		return fmt.Sprintf(`# Prompt Filter Policy
# Filters requests based on prompt content patterns
type: PromptFilterPolicy
name: %s
config:
  # List of regex patterns to block
  patterns:
    - "(?i)password"
    - "(?i)secret"
    - "(?i)api.?key"
`, req.Name)

	case "AttributionPolicy":
		return fmt.Sprintf(`# Attribution Policy
# Tracks data usage attribution for audit purposes
type: AttributionPolicy
name: %s
config:
  # Fields to track for attribution
  track_fields:
    - user_id
    - endpoint_slug
    - timestamp
  # Attribution log path (optional)
  log_path: .attribution_log.jsonl
`, req.Name)

	case "ManualReviewPolicy":
		return fmt.Sprintf(`# Manual Review Policy
# Requires manual approval for requests
type: ManualReviewPolicy
name: %s
config:
  # Review timeout in seconds (request denied if not approved in time)
  timeout_seconds: 3600
  # Notification webhook URL (optional)
  webhook_url: ""
`, req.Name)

	case "TransactionPolicy":
		return fmt.Sprintf(`# Transaction Policy
# Manages credit/token-based transactions
type: TransactionPolicy
name: %s
config:
  # Cost per request (in credits/tokens)
  cost_per_request: 1
  # Initial balance for new users
  initial_balance: 100
`, req.Name)

	case "AllOfPolicy":
		// Build child policies list
		childPoliciesYAML := ""
		if len(req.ChildPolicies) > 0 {
			for _, child := range req.ChildPolicies {
				childPoliciesYAML += fmt.Sprintf("    - %s\n", child)
			}
		} else {
			childPoliciesYAML = "    - policy_name_1\n    - policy_name_2\n"
		}
		return fmt.Sprintf(`# All-Of Policy (Composite)
# ALL child policies must pass for the request to be allowed
type: AllOfPolicy
name: %s
config:
  # List of policy names that must ALL pass
  policies:
%s`, req.Name, childPoliciesYAML)

	case "AnyOfPolicy":
		// Build child policies list
		childPoliciesYAML := ""
		if len(req.ChildPolicies) > 0 {
			for _, child := range req.ChildPolicies {
				childPoliciesYAML += fmt.Sprintf("    - %s\n", child)
			}
		} else {
			childPoliciesYAML = "    - policy_name_1\n    - policy_name_2\n"
		}
		return fmt.Sprintf(`# Any-Of Policy (Composite)
# At least ONE child policy must pass for the request to be allowed
type: AnyOfPolicy
name: %s
config:
  # List of policy names where at least one must pass
  policies:
%s`, req.Name, childPoliciesYAML)

	case "NotPolicy":
		// Build child policies list (NotPolicy typically wraps one policy)
		childPolicyName := "policy_to_negate"
		if len(req.ChildPolicies) > 0 {
			childPolicyName = req.ChildPolicies[0]
		}
		denyReason := req.DenyReason
		if denyReason == "" {
			denyReason = "Access denied by policy negation"
		}
		return fmt.Sprintf(`# Not Policy (Composite)
# Inverts the result of the wrapped policy
type: NotPolicy
name: %s
config:
  # The policy to negate (deny becomes allow, allow becomes deny)
  policy: %s
  # Reason shown when the negated policy blocks access
  deny_reason: "%s"
`, req.Name, childPolicyName, denyReason)

	default:
		// Generic template for unknown types
		return fmt.Sprintf(`# Policy configuration
type: %s
name: %s
config: {}
`, req.Type, req.Name)
	}
}

// CreatePolicyFile creates a new policy file with a template based on the request.
func (a *App) CreatePolicyFile(slug string, req NewPolicyRequest) error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	if req.Name == "" {
		return fmt.Errorf("policy name is required")
	}

	if req.Type == "" {
		return fmt.Errorf("policy type is required")
	}

	// Generate filename from policy name
	filename := slugifyFilename(req.Name)

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

// slugify converts a name to a URL-safe slug.
// E.g., "My Cool Model" -> "my-cool-model"
func slugify(name string) string {
	slug := strings.ToLower(name)
	slug = strings.ReplaceAll(slug, " ", "-")
	slug = strings.ReplaceAll(slug, "_", "-")

	// Keep only alphanumeric and hyphens
	var result strings.Builder
	for _, r := range slug {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' {
			result.WriteRune(r)
		}
	}
	slug = result.String()

	// Remove consecutive hyphens
	for strings.Contains(slug, "--") {
		slug = strings.ReplaceAll(slug, "--", "-")
	}
	slug = strings.Trim(slug, "-")

	return slug
}

// CheckEndpointExists checks if an endpoint with the given name already exists.
// Returns the generated slug and whether it exists.
func (a *App) CheckEndpointExists(name string) (string, bool) {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if a.config == nil {
		return "", false
	}

	slug := slugify(name)
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

	if slug == "" {
		return fmt.Errorf("endpoint slug is required")
	}

	// Security: Validate slug to prevent path traversal
	if strings.Contains(slug, "..") || strings.Contains(slug, "/") || strings.Contains(slug, "\\") {
		return fmt.Errorf("invalid endpoint slug")
	}

	endpointDir := filepath.Join(a.config.EndpointsPath, slug)

	// Verify endpoint exists
	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		return fmt.Errorf("endpoint not found: %s", slug)
	}

	// Delete the entire endpoint directory and all contents
	if err := os.RemoveAll(endpointDir); err != nil {
		return fmt.Errorf("failed to delete endpoint: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Deleted endpoint: %s", slug))

	// Notify frontend about the change
	runtime.EventsEmit(a.ctx, "app:endpoints-changed", nil)

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
	if req.Type != "model" && req.Type != "data_source" {
		return "", fmt.Errorf("endpoint type must be 'model' or 'data_source'")
	}

	// Generate slug from name
	slug := slugify(req.Name)
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
	runnerContent := getRunnerTemplate(req.Type)
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
  mode: subprocess
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

// getRunnerTemplate returns the runner.py template content for the given endpoint type.
func getRunnerTemplate(endpointType string) string {
	if endpointType == "model" {
		return `"""
Model endpoint handler.

This handler processes incoming requests to your model endpoint.
"""


def handler(messages: list, context: dict = None) -> str:
    """
    Echo back the last user message.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        context: Optional context metadata

    Returns:
        The echoed message
    """
    # Find the last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return f"Echo: {content}"
    return "Hello world!"
`
	}

	// data_source type
	return `"""
Data Source Endpoint Runner

This endpoint provides access to data sources (databases, APIs, files).
Implement the query() function to handle data requests.
"""


def query(request):
    """
    Query data from your data source.

    Args:
        request: The incoming request object containing:
            - query: SQL query or search parameters
            - filters: Optional filter criteria
            - user: User information for access control

    Returns:
        Data matching the query - typically a dict with 'data' array
    """
    query_text = getattr(request, 'query', '')

    # TODO: Implement your data source logic here
    # Example: Execute SQL, call external API, read files, etc.

    return {
        "data": [],
        "count": 0,
        "message": f"Query received: {query_text}"
    }
`
}
