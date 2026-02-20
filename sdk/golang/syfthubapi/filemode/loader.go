// Package filemode provides file-based endpoint configuration and management.
package filemode

import (
	"bufio"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// EndpointConfig represents the configuration from README.md frontmatter.
type EndpointConfig struct {
	Slug        string        `yaml:"slug"`
	Type        string        `yaml:"type"` // "model" or "data_source"
	Name        string        `yaml:"name"`
	Description string        `yaml:"description"`
	Enabled     *bool         `yaml:"enabled"` // Pointer to detect if set
	Version     string        `yaml:"version"`
	Env         EnvConfig     `yaml:"env"`
	Runtime     RuntimeConfig `yaml:"runtime"`
}

// EnvConfig specifies environment variable requirements.
type EnvConfig struct {
	Required []string `yaml:"required"`
	Optional []string `yaml:"optional"`
	Inherit  []string `yaml:"inherit"`
}

// RuntimeConfig specifies runtime settings.
type RuntimeConfig struct {
	Mode    string   `yaml:"mode"`    // "subprocess" (default)
	Workers int      `yaml:"workers"` // Number of worker processes
	Timeout int      `yaml:"timeout"` // Execution timeout in seconds
	Extras  []string `yaml:"extras"`  // pip extras groups
}

// LoadedEndpoint represents a fully loaded endpoint from the file system.
type LoadedEndpoint struct {
	Config        *EndpointConfig
	Dir           string   // Directory containing the endpoint
	RunnerPath    string   // Path to runner.py
	EnvVars       []string // Environment variables
	PolicyConfigs []syfthubapi.PolicyConfig
	StoreConfig   *syfthubapi.StoreConfig
	ReadmeBody    string // README markdown content (after frontmatter)
}

// Loader loads endpoints from the file system.
type Loader struct {
	basePath string
	logger   *slog.Logger
}

// NewLoader creates a new endpoint loader.
func NewLoader(basePath string, logger *slog.Logger) *Loader {
	if logger == nil {
		logger = slog.Default()
	}
	return &Loader{
		basePath: basePath,
		logger:   logger,
	}
}

// LoadAll loads all endpoints from the base path.
func (l *Loader) LoadAll() ([]*LoadedEndpoint, error) {
	entries, err := os.ReadDir(l.basePath)
	if err != nil {
		return nil, &syfthubapi.FileLoadError{
			Path:    l.basePath,
			Message: "failed to read directory",
			Cause:   err,
		}
	}

	var endpoints []*LoadedEndpoint
	var errors []error

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		// Skip hidden directories and common ignore patterns
		name := entry.Name()
		if strings.HasPrefix(name, ".") || strings.HasPrefix(name, "_") {
			continue
		}
		if name == "__pycache__" || name == "node_modules" || name == ".venv" {
			continue
		}

		endpointDir := filepath.Join(l.basePath, name)
		endpoint, err := l.LoadEndpoint(endpointDir)
		if err != nil {
			l.logger.Warn("failed to load endpoint",
				"dir", name,
				"error", err,
			)
			errors = append(errors, err)
			continue
		}

		endpoints = append(endpoints, endpoint)
	}

	if len(endpoints) == 0 && len(errors) > 0 {
		return nil, fmt.Errorf("no endpoints loaded, %d errors occurred", len(errors))
	}

	l.logger.Info("loaded endpoints",
		"count", len(endpoints),
		"errors", len(errors),
	)

	return endpoints, nil
}

// LoadEndpoint loads a single endpoint from a directory.
func (l *Loader) LoadEndpoint(dir string) (*LoadedEndpoint, error) {
	// Check for README.md
	readmePath := filepath.Join(dir, "README.md")
	if _, err := os.Stat(readmePath); os.IsNotExist(err) {
		return nil, &syfthubapi.FileLoadError{
			Path:    dir,
			Message: "README.md not found",
		}
	}

	// Check for runner.py
	runnerPath := filepath.Join(dir, "runner.py")
	if _, err := os.Stat(runnerPath); os.IsNotExist(err) {
		return nil, &syfthubapi.FileLoadError{
			Path:    dir,
			Message: "runner.py not found",
		}
	}

	// Parse README.md frontmatter and body
	config, readmeBody, err := l.parseReadme(readmePath)
	if err != nil {
		return nil, err
	}

	// Use directory name as slug if not specified
	if config.Slug == "" {
		config.Slug = filepath.Base(dir)
	}

	// Set defaults
	if config.Enabled == nil {
		enabled := true
		config.Enabled = &enabled
	}
	if config.Runtime.Mode == "" {
		config.Runtime.Mode = "subprocess"
	}
	if config.Runtime.Timeout == 0 {
		config.Runtime.Timeout = 30
	}
	if config.Runtime.Workers == 0 {
		config.Runtime.Workers = 1
	}

	// Load environment variables
	envVars, err := l.loadEnvVars(dir, &config.Env)
	if err != nil {
		return nil, err
	}

	// Load policies
	policyConfigs, storeConfig, err := l.loadPolicies(dir)
	if err != nil {
		l.logger.Warn("failed to load policies",
			"dir", dir,
			"error", err,
		)
		// Continue without policies
	}

	return &LoadedEndpoint{
		Config:        config,
		Dir:           dir,
		RunnerPath:    runnerPath,
		EnvVars:       envVars,
		PolicyConfigs: policyConfigs,
		StoreConfig:   storeConfig,
		ReadmeBody:    readmeBody,
	}, nil
}

// parseReadme parses YAML frontmatter from README.md and returns the markdown body.
// Returns (config, body, error) where body is the markdown content after frontmatter.
func (l *Loader) parseReadme(path string) (*EndpointConfig, string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "failed to open file",
			Cause:   err,
		}
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)

	// Look for opening ---
	if !scanner.Scan() {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "empty file",
		}
	}

	firstLine := strings.TrimSpace(scanner.Text())
	if firstLine != "---" {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "missing YAML frontmatter (expected '---')",
		}
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
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "error reading file",
			Cause:   err,
		}
	}

	if !foundClose {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "unclosed YAML frontmatter (missing closing '---')",
		}
	}

	// Collect body content (everything after frontmatter)
	var bodyLines []string
	for scanner.Scan() {
		bodyLines = append(bodyLines, scanner.Text())
	}

	if err := scanner.Err(); err != nil {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "error reading file body",
			Cause:   err,
		}
	}

	// Parse YAML
	yamlContent := strings.Join(yamlLines, "\n")
	var config EndpointConfig
	if err := yaml.Unmarshal([]byte(yamlContent), &config); err != nil {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "invalid YAML frontmatter",
			Cause:   err,
		}
	}

	// Validate required fields
	if config.Name == "" {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "missing required field: name",
		}
	}
	if config.Type == "" {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: "missing required field: type",
		}
	}
	if config.Type != "model" && config.Type != "data_source" {
		return nil, "", &syfthubapi.FileLoadError{
			Path:    path,
			Message: fmt.Sprintf("invalid type: %s (must be 'model' or 'data_source')", config.Type),
		}
	}

	// Trim leading/trailing whitespace from body
	body := strings.TrimSpace(strings.Join(bodyLines, "\n"))

	return &config, body, nil
}

// loadEnvVars loads environment variables from .env file and validates requirements.
func (l *Loader) loadEnvVars(dir string, envConfig *EnvConfig) ([]string, error) {
	envVars := []string{}

	// Load from .env file if exists
	envPath := filepath.Join(dir, ".env")
	if _, err := os.Stat(envPath); err == nil {
		vars, err := loadDotEnv(envPath)
		if err != nil {
			return nil, &syfthubapi.FileLoadError{
				Path:    envPath,
				Message: "failed to load .env file",
				Cause:   err,
			}
		}
		envVars = append(envVars, vars...)
	}

	// Check required variables
	envMap := envVarsToMap(envVars)
	for _, req := range envConfig.Required {
		// Check endpoint .env first, then system env
		if _, ok := envMap[req]; !ok {
			if os.Getenv(req) == "" {
				return nil, &syfthubapi.FileLoadError{
					Path:    dir,
					Message: fmt.Sprintf("missing required environment variable: %s", req),
				}
			}
			// Add from system env
			envVars = append(envVars, fmt.Sprintf("%s=%s", req, os.Getenv(req)))
		}
	}

	// Add inherited variables from system env
	for _, inherit := range envConfig.Inherit {
		if val := os.Getenv(inherit); val != "" {
			if _, ok := envMap[inherit]; !ok {
				envVars = append(envVars, fmt.Sprintf("%s=%s", inherit, val))
			}
		}
	}

	return envVars, nil
}

// loadPolicies loads individual policy files from a policy/ subdirectory.
// Returns the policy configurations and store configuration for use with the Python runner.
func (l *Loader) loadPolicies(dir string) ([]syfthubapi.PolicyConfig, *syfthubapi.StoreConfig, error) {
	l.logger.Info("[POLICY-LOAD] Looking for policies in endpoint directory",
		"dir", dir,
	)
	policyDir := filepath.Join(dir, "policy")
	if _, err := os.Stat(policyDir); os.IsNotExist(err) {
		l.logger.Info("[POLICY-LOAD] No policy/ directory found",
			"dir", dir,
		)
		return nil, nil, nil // No policies
	}

	l.logger.Info("[POLICY-LOAD] Found policy/ directory, loading individual policy files",
		"path", policyDir,
	)

	entries, err := os.ReadDir(policyDir)
	if err != nil {
		l.logger.Error("[POLICY-LOAD] Failed to read policy directory",
			"path", policyDir,
			"error", err,
		)
		return nil, nil, &syfthubapi.FileLoadError{
			Path:    policyDir,
			Message: "failed to read policy directory",
			Cause:   err,
		}
	}

	var policies []syfthubapi.PolicyConfig

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		name := entry.Name()
		ext := filepath.Ext(name)
		if ext != ".yaml" && ext != ".yml" {
			continue
		}

		policyPath := filepath.Join(policyDir, name)
		l.logger.Debug("[POLICY-LOAD] Loading policy file",
			"path", policyPath,
		)

		data, err := os.ReadFile(policyPath)
		if err != nil {
			l.logger.Warn("[POLICY-LOAD] Failed to read policy file",
				"path", policyPath,
				"error", err,
			)
			continue
		}

		// Parse individual policy file
		var policy syfthubapi.PolicyConfig
		if err := yaml.Unmarshal(data, &policy); err != nil {
			l.logger.Warn("[POLICY-LOAD] Failed to parse policy YAML",
				"path", policyPath,
				"error", err,
			)
			continue
		}

		// Normalize the policy type (convert PascalCase to snake_case)
		policy.Type = normalizePolicyType(policy.Type)

		l.logger.Info("[POLICY-LOAD] Loaded policy from file",
			"path", policyPath,
			"name", policy.Name,
			"type", policy.Type,
			"config", fmt.Sprintf("%+v", policy.Config),
		)

		policies = append(policies, policy)
	}

	if len(policies) == 0 {
		l.logger.Info("[POLICY-LOAD] No valid policy files found in policy/ directory",
			"path", policyDir,
		)
		return nil, nil, nil
	}

	// Validate policies
	if err := l.validatePolicies(policies); err != nil {
		l.logger.Error("[POLICY-LOAD] Policy validation failed",
			"path", policyDir,
			"error", err,
		)
		return nil, nil, &syfthubapi.FileLoadError{
			Path:    policyDir,
			Message: "policy validation failed",
			Cause:   err,
		}
	}

	l.logger.Info("[POLICY-LOAD] All policies from directory validated successfully",
		"path", policyDir,
		"count", len(policies),
	)

	// Create default store config for directory-based policies
	storeConfig := &syfthubapi.StoreConfig{
		Type: "sqlite",
		Path: filepath.Join(policyDir, "store.db"),
	}

	return policies, storeConfig, nil
}

// normalizePolicyType converts policy type names to the format expected by Python.
// Handles both PascalCase (e.g., "AccessGroupPolicy") and snake_case (e.g., "access_group").
func normalizePolicyType(t string) string {
	// Map of PascalCase to snake_case conversions
	typeMap := map[string]string{
		"AccessGroupPolicy":  syfthubapi.PolicyTypeAccessGroup,
		"RateLimitPolicy":    syfthubapi.PolicyTypeRateLimit,
		"TokenLimitPolicy":   syfthubapi.PolicyTypeTokenLimit,
		"PromptFilterPolicy": syfthubapi.PolicyTypePromptFilter,
		"AttributionPolicy":  syfthubapi.PolicyTypeAttribution,
		"ManualReviewPolicy": syfthubapi.PolicyTypeManualReview,
		"TransactionPolicy":  syfthubapi.PolicyTypeTransaction,
		"CustomPolicy":       syfthubapi.PolicyTypeCustom,
		"AllOfPolicy":        syfthubapi.PolicyTypeAllOf,
		"AnyOfPolicy":        syfthubapi.PolicyTypeAnyOf,
		"NotPolicy":          syfthubapi.PolicyTypeNot,
	}

	if normalized, ok := typeMap[t]; ok {
		return normalized
	}

	// Already in correct format or unknown type
	return t
}

// validatePolicies validates a list of policy configurations.
func (l *Loader) validatePolicies(policies []syfthubapi.PolicyConfig) error {
	seen := make(map[string]bool)

	for _, p := range policies {
		// Check name
		if p.Name == "" {
			return fmt.Errorf("policy missing required field: name")
		}
		if seen[p.Name] {
			return fmt.Errorf("duplicate policy name: %s", p.Name)
		}
		seen[p.Name] = true

		// Check type
		if p.Type == "" {
			return fmt.Errorf("policy '%s' missing required field: type", p.Name)
		}
		if !syfthubapi.ValidPolicyTypes[p.Type] {
			return fmt.Errorf("policy '%s' has unknown type: %s", p.Name, p.Type)
		}

		// Validate composite policy references
		if p.Type == syfthubapi.PolicyTypeAllOf || p.Type == syfthubapi.PolicyTypeAnyOf {
			refs, ok := p.Config["policies"].([]any)
			if !ok || len(refs) == 0 {
				return fmt.Errorf("policy '%s' requires 'policies' list in config", p.Name)
			}
			for _, ref := range refs {
				refName, ok := ref.(string)
				if !ok {
					return fmt.Errorf("policy '%s' has invalid policy reference", p.Name)
				}
				if !seen[refName] {
					return fmt.Errorf("policy '%s' references undefined policy '%s'", p.Name, refName)
				}
			}
		}

		if p.Type == syfthubapi.PolicyTypeNot {
			ref, ok := p.Config["policy"].(string)
			if !ok || ref == "" {
				return fmt.Errorf("policy '%s' requires 'policy' reference in config", p.Name)
			}
			if !seen[ref] {
				return fmt.Errorf("policy '%s' references undefined policy '%s'", p.Name, ref)
			}
		}
	}

	return nil
}

// loadDotEnv loads environment variables from a .env file.
func loadDotEnv(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var vars []string
	scanner := bufio.NewScanner(file)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		// Parse KEY=value format
		idx := strings.Index(line, "=")
		if idx == -1 {
			continue
		}

		key := strings.TrimSpace(line[:idx])
		value := strings.TrimSpace(line[idx+1:])

		// Remove surrounding quotes
		if len(value) >= 2 {
			if (value[0] == '"' && value[len(value)-1] == '"') ||
				(value[0] == '\'' && value[len(value)-1] == '\'') {
				value = value[1 : len(value)-1]
			}
		}

		vars = append(vars, fmt.Sprintf("%s=%s", key, value))
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return vars, nil
}

// envVarsToMap converts a slice of KEY=value strings to a map.
func envVarsToMap(vars []string) map[string]string {
	m := make(map[string]string)
	for _, v := range vars {
		idx := strings.Index(v, "=")
		if idx != -1 {
			m[v[:idx]] = v[idx+1:]
		}
	}
	return m
}

// ToEndpointType converts string type to EndpointType.
func ToEndpointType(t string) syfthubapi.EndpointType {
	switch t {
	case "data_source":
		return syfthubapi.EndpointTypeDataSource
	case "model":
		return syfthubapi.EndpointTypeModel
	default:
		return syfthubapi.EndpointTypeModel
	}
}
