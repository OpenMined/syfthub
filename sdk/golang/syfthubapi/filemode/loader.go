// Package filemode provides file-based endpoint configuration and management.
package filemode

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// EndpointConfig represents the configuration from README.md frontmatter.
type EndpointConfig struct {
	Slug        string                  `yaml:"slug"`
	Type        string                  `yaml:"type"` // "model", "data_source", or "agent"
	Name        string                  `yaml:"name"`
	Description string                  `yaml:"description"`
	Enabled     *bool                   `yaml:"enabled"` // Pointer to detect if set
	Version     string                  `yaml:"version"`
	Env         EnvConfig               `yaml:"env"`
	Runtime     RuntimeConfig           `yaml:"runtime"`
	Container   EndpointContainerConfig `yaml:"container"`

	// AcceptsAttachments opts an agent endpoint into receiving file attachments
	// from the caller. Default false. See docs/architecture/attachments.md.
	// Only meaningful for agent endpoints.
	AcceptsAttachments bool `yaml:"accepts_attachments"`

	// Sandbox describes the in-container isolation policy for runner.py.
	// Only takes effect in container mode; ignored in subprocess (host) mode,
	// which is documented as insecure.
	Sandbox SandboxConfig `yaml:"sandbox"`
}

// SandboxConfig captures the per-endpoint isolation intent. Every field has a
// safe default so endpoints that omit `sandbox:` get sensible behavior.
type SandboxConfig struct {
	// Workspace describes the writable scratch dir for the handler.
	Workspace WorkspaceConfig `yaml:"workspace"`

	// ExposeEnv is the explicit allowlist of env-var names the handler can
	// see at runtime. When nil/empty, defaults to EnvConfig.Required so
	// existing endpoints keep working without a frontmatter change.
	ExposeEnv []string `yaml:"expose_env"`

	// SubprocessEnv is the allowlist of env-var names that pass through
	// to subprocesses the handler spawns. Vars NOT in this list are
	// stripped from the subprocess's environment regardless of whether
	// runner.py can see them. Essentials (PATH, HOME, LANG, …) are
	// always preserved. Default empty → subprocesses inherit only
	// essentials; .env secrets stay inside runner.py.
	//
	// Use this for vars that need to reach a child binary (e.g.
	// CLAUDE_SKIP_PERMISSIONS for the claude-code CLI). API keys and
	// other secrets should NOT be listed here — the LLM agent inside
	// can otherwise be prompted to read them via /proc/self/environ
	// or by running `env` through its shell tool.
	SubprocessEnv []string `yaml:"subprocess_env"`

	// ExposeResources lists endpoint-relative paths that are exposed
	// read-only to the handler in addition to *.py files. Use this for
	// prompt templates, static data, etc.
	ExposeResources []string `yaml:"expose_resources"`

	// Network controls outbound network access for the handler.
	Network NetworkConfig `yaml:"network"`

	// AllowSubprocess, when true, lets the handler spawn child processes.
	// Default false — the audit hook blocks subprocess.Popen.
	AllowSubprocess bool `yaml:"allow_subprocess"`

	// Limits caps CPU, memory, wall-clock, and tmpfs usage.
	Limits LimitsConfig `yaml:"limits"`
}

// WorkspaceConfig describes the handler's writable scratch dir.
type WorkspaceConfig struct {
	// Path is the endpoint-relative subdir that holds workspace data.
	// Default: "workspace".
	Path string `yaml:"path"`

	// Scope selects how the workspace is partitioned per invocation:
	//   "shared"       — one dir shared across all invocations (default for
	//                    one-shot endpoints)
	//   "per_user"     — one dir per authenticated user
	//   "per_session"  — one dir per agent session, deleted on session end
	//                    (default for agent endpoints)
	Scope string `yaml:"scope"`

	// QuotaMB caps the workspace size in megabytes. 0 means unlimited.
	QuotaMB int `yaml:"quota_mb"`
}

// NetworkConfig describes the handler's outbound network access.
type NetworkConfig struct {
	// Mode: "open" (default), "allowlist", or "none".
	Mode string `yaml:"mode"`

	// Hosts is the allowlist of FQDNs reachable when Mode == "allowlist".
	Hosts []string `yaml:"hosts"`
}

// LimitsConfig caps resource usage. Zero values mean "use the container's
// default" (i.e., the global ContainerConfig limits).
type LimitsConfig struct {
	CPUCores       float64 `yaml:"cpu_cores"`
	MemoryMB       int     `yaml:"memory_mb"`
	TimeoutSeconds int     `yaml:"timeout_seconds"`
	TmpfsMB        int     `yaml:"tmpfs_mb"`
}

// EnvConfig specifies environment variable requirements.
type EnvConfig struct {
	Required []string `yaml:"required"`
	Optional []string `yaml:"optional"`
	Inherit  []string `yaml:"inherit"`
}

// RuntimeConfig specifies runtime settings for subprocess execution.
type RuntimeConfig struct {
	Workers int      `yaml:"workers"` // Number of worker processes
	Timeout int      `yaml:"timeout"` // Execution timeout in seconds
	Extras  []string `yaml:"extras"`  // pip extras groups
}

// EndpointContainerConfig holds per-endpoint container overrides.
// When specified in the README.md frontmatter under "container:", these
// values override the global ContainerConfig for this endpoint only.
type EndpointContainerConfig struct {
	Image  string           `yaml:"image"`  // Registry image reference (e.g., "myorg/custom-runner:v2")
	Mounts []ContainerMount `yaml:"mounts"` // Extra bind mounts from host into the container
}

// ContainerMount declares a host path to bind-mount into the container.
// Source supports ~ expansion and $VAR substitution.
type ContainerMount struct {
	Source   string `yaml:"source"`    // Host path (e.g., "~/.claude/.credentials.json")
	Target   string `yaml:"target"`    // Container path (e.g., "/home/runner/.claude/.credentials.json")
	ReadOnly bool   `yaml:"read_only"` // Mount read-only (default: false)
}

// LoadedEndpoint represents a fully loaded endpoint from the file system.
type LoadedEndpoint struct {
	Config     *EndpointConfig
	Dir        string // Directory containing the endpoint
	RunnerPath string // Path to runner.py

	// EnvVars is the full env (required + inherit) used by the host-side
	// policy_manager runner. Retained for backwards compatibility — when
	// HandlerEnv is set, prefer that for the handler process.
	EnvVars []string

	// HandlerEnv is the narrow allowlist passed to the handler subprocess.
	// Built from EnvVars intersected with SandboxConfig.ExposeEnv. Equal to
	// EnvVars when no expose_env is configured (legacy behavior).
	HandlerEnv []string

	// PolicyEnv is the full env exposed to the host-side policy runner.
	// Includes everything in EnvVars; never narrowed.
	PolicyEnv []string

	PolicyConfigs []syfthubapi.PolicyConfig
	StoreConfig   *syfthubapi.StoreConfig
	ReadmeBody    string // README markdown content (after frontmatter)
	HasDockerfile bool   // true if Dockerfile exists in endpoint dir
}

// Loader loads endpoints from the file system.
type Loader struct {
	basePath string
	logger   *slog.Logger
}

// NewLoader creates a new endpoint loader.
// It ensures the base directory exists so that first-run or manual config
// paths are created eagerly rather than on every LoadAll call.
func NewLoader(basePath string, logger *slog.Logger) *Loader {
	if logger == nil {
		logger = slog.Default()
	}
	// Best-effort: create the directory at init time so the first LoadAll
	// doesn't fail with "no such directory" on a fresh install. Errors
	// here are non-fatal; LoadAll will surface them when it reads.
	_ = os.MkdirAll(basePath, 0755)
	return &Loader{
		basePath: basePath,
		logger:   logger,
	}
}

// LoadAll loads all endpoints from the base path.
func (l *Loader) LoadAll() ([]*LoadedEndpoint, error) {
	entries, err := os.ReadDir(l.basePath)
	if err != nil {
		return nil, fmt.Errorf("file load %s: failed to read directory: %w", l.basePath, err)
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
	readmePath := filepath.Join(dir, "README.md")
	runnerPath := filepath.Join(dir, "runner.py")

	// Verify runner.py exists (read it to avoid TOCTOU; the file is small).
	if _, err := os.ReadFile(runnerPath); err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("file load %s: runner.py not found", dir)
		}
		return nil, fmt.Errorf("file load %s: failed to read runner.py: %w", dir, err)
	}

	// Parse README.md frontmatter and body (parseReadme opens the file directly,
	// so there is no separate stat-then-read gap).
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
	if config.Runtime.Timeout == 0 {
		config.Runtime.Timeout = 30
	}
	if config.Runtime.Workers == 0 {
		config.Runtime.Workers = 1
	}

	// Check setup status before env var validation.
	// When setup is incomplete, required env vars may not exist yet,
	// so we disable the endpoint and skip strict validation.
	var envVars []string
	status, err := nodeops.GetSetupStatus(dir)
	if err != nil {
		l.logger.Warn("failed to check setup status", "dir", dir, "error", err)
	}
	if status != nil && !status.IsComplete {
		l.logger.Warn("endpoint setup incomplete, disabling",
			"slug", config.Slug,
			"pending", status.PendingSteps,
			"expired", status.ExpiredSteps,
		)
		enabled := false
		config.Enabled = &enabled
	} else {
		// Load environment variables (only when setup is complete or no setup.yaml)
		envVars, err = l.loadEnvVars(dir, &config.Env)
		if err != nil {
			return nil, err
		}
	}

	// Load policies
	policyConfigs, storeConfig, err := l.loadPolicies(dir)
	if err != nil {
		l.logger.Warn("failed to load policies", "dir", dir, "error", err)
	}

	// Detect Dockerfile in endpoint directory for custom container image builds.
	hasDockerfile := false
	if _, err := os.Stat(filepath.Join(dir, "Dockerfile")); err == nil {
		hasDockerfile = true
	}
	if config.Container.Image != "" && hasDockerfile {
		l.logger.Warn("endpoint has both container.image and Dockerfile; using frontmatter image",
			"slug", config.Slug,
			"image", config.Container.Image,
		)
	}

	handlerEnv, policyEnv := splitEnvForSandbox(envVars, &config.Sandbox)

	return &LoadedEndpoint{
		Config:        config,
		Dir:           dir,
		RunnerPath:    runnerPath,
		EnvVars:       envVars,
		HandlerEnv:    handlerEnv,
		PolicyEnv:     policyEnv,
		PolicyConfigs: policyConfigs,
		StoreConfig:   storeConfig,
		ReadmeBody:    readmeBody,
		HasDockerfile: hasDockerfile,
	}, nil
}

// splitEnvForSandbox separates the loaded env into two sets:
//
//   - HandlerEnv — what the in-bwrap handler subprocess sees via os.environ.
//   - PolicyEnv  — the full env, retained for the host-side policy runner
//     which never enters the container.
//
// DEFAULT (no sandbox.expose_env): the handler sees the FULL .env. This
// matches pre-sandbox behavior where the runner subprocess received every
// var declared in the endpoint's .env file. Most endpoints put things in
// .env precisely because the handler needs them — narrowing by default
// breaks the contract silently.
//
// OPT-IN narrowing via sandbox.expose_env: when the developer wants to
// hide specific vars from the handler (e.g. a billing token that only
// the host-side policy runner consumes), they declare a positive
// allowlist. HandlerEnv is then the intersection of envVars and the
// allowlist.
func splitEnvForSandbox(envVars []string, sb *SandboxConfig) (handler, policy []string) {
	// Policy runner always sees the full env. Returned as a fresh slice so
	// the caller can mutate one set without disturbing the other.
	policy = append(policy, envVars...)

	// No explicit allowlist → handler sees the full .env (legacy default).
	if sb == nil || len(sb.ExposeEnv) == 0 {
		handler = append(handler, envVars...)
		return handler, policy
	}

	// Explicit allowlist narrows the handler view.
	allow := map[string]struct{}{}
	for _, k := range sb.ExposeEnv {
		allow[k] = struct{}{}
	}
	for _, kv := range envVars {
		key, _, ok := strings.Cut(kv, "=")
		if !ok || key == "" {
			continue
		}
		if _, ok := allow[key]; ok {
			handler = append(handler, kv)
		}
	}
	return handler, policy
}

// parseReadme parses YAML frontmatter from README.md and returns the markdown body.
// Returns (config, body, error) where body is the markdown content after frontmatter.
func (l *Loader) parseReadme(path string) (*EndpointConfig, string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, "", fmt.Errorf("file load %s: failed to open file: %w", path, err)
	}
	defer file.Close()

	yamlBytes, body, err := nodeops.SplitFrontmatter(file)
	if err != nil {
		return nil, "", fmt.Errorf("file load %s: %w", path, err)
	}

	var config EndpointConfig
	if err := yaml.Unmarshal(yamlBytes, &config); err != nil {
		return nil, "", fmt.Errorf("file load %s: invalid YAML frontmatter: %w", path, err)
	}

	// Validate required fields
	if config.Name == "" {
		return nil, "", fmt.Errorf("file load %s: missing required field: name", path)
	}
	if config.Type == "" {
		return nil, "", fmt.Errorf("file load %s: missing required field: type", path)
	}
	if !syfthubapi.IsValidEndpointType(config.Type) {
		return nil, "", fmt.Errorf("file load %s: invalid type: %s (must be one of: %v)", path, config.Type, syfthubapi.ValidEndpointTypes)
	}

	return &config, body, nil
}

// loadEnvVars loads environment variables from .env file and validates requirements.
func (l *Loader) loadEnvVars(dir string, envConfig *EnvConfig) ([]string, error) {
	envVars := []string{}

	// Load from .env file (loadDotEnv returns an empty slice if absent).
	envPath := filepath.Join(dir, ".env")
	vars, err := loadDotEnv(envPath)
	if err != nil {
		return nil, fmt.Errorf("file load %s: failed to load .env file: %w", envPath, err)
	}
	envVars = append(envVars, vars...)

	// Check required variables. Convert "KEY=value" strings into structured
	// EnvVar entries so nodeops.EnvVarsToMap can index them.
	envVarStructs := make([]nodeops.EnvVar, 0, len(envVars))
	for _, v := range envVars {
		if idx := strings.Index(v, "="); idx != -1 {
			envVarStructs = append(envVarStructs, nodeops.EnvVar{Key: v[:idx], Value: v[idx+1:]})
		}
	}
	envMap := nodeops.EnvVarsToMap(envVarStructs)
	for _, req := range envConfig.Required {
		// Check endpoint .env first, then system env
		if _, ok := envMap[req]; !ok {
			if os.Getenv(req) == "" {
				return nil, fmt.Errorf("file load %s: missing required environment variable: %s", dir, req)
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
		return nil, nil, fmt.Errorf("file load %s: failed to read policy directory: %w", policyDir, err)
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
		return nil, nil, fmt.Errorf("file load %s: policy validation failed: %w", policyDir, err)
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
// Delegates to nodeops.ReadEnvFile for canonical parsing of blank lines,
// comments, quote stripping, and KEY=value format.
func loadDotEnv(path string) ([]string, error) {
	envVars, err := nodeops.ReadEnvFile(path)
	if err != nil {
		return nil, err
	}
	result := make([]string, len(envVars))
	for i, ev := range envVars {
		result[i] = ev.Key + "=" + ev.Value
	}
	return result, nil
}

// ToEndpointType converts string type to EndpointType.
func ToEndpointType(t string) syfthubapi.EndpointType {
	switch t {
	case "data_source":
		return syfthubapi.EndpointTypeDataSource
	case "model":
		return syfthubapi.EndpointTypeModel
	case "agent":
		return syfthubapi.EndpointTypeAgent
	default:
		return syfthubapi.EndpointTypeModel
	}
}
