// Package main provides endpoint file operations for the SyftHub Desktop GUI.
// These methods enable reading and writing endpoint files (runner.py, README.md, .env, etc.)
package main

import (
	"database/sql"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	goruntime "runtime"
	"strings"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"
	"gopkg.in/yaml.v3"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// reloadAfterEndpointMutation forces a fresh load of endpoints after a file
// mutation that should take effect immediately (policy changes, etc.). Errors
// are logged but not propagated — the mutation itself already succeeded, and
// the fallback file-watcher reload should still kick in. Notifies the frontend
// so the UI can refresh derived state. Safe to call when core is not yet wired.
func (a *App) reloadAfterEndpointMutation(slug string) {
	a.mu.RLock()
	core := a.core
	a.mu.RUnlock()
	if core == nil {
		return
	}
	if err := core.ReloadEndpoints(); err != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("Failed to reload endpoints after mutation (slug=%s): %v", slug, err))
	}
	a.notifyEndpointsChanged()
}

// EndpointDetail provides full endpoint information for the detail view.
type EndpointDetail struct {
	Slug          string           `json:"slug"`
	Name          string           `json:"name"`
	Description   string           `json:"description"`
	Type          string           `json:"type"`
	Version       string           `json:"version"`
	Enabled       bool             `json:"enabled"`
	HasReadme     bool             `json:"hasReadme"`
	HasPolicies   bool             `json:"hasPolicies"`
	DepsCount     int              `json:"depsCount"`
	EnvCount      int              `json:"envCount"`
	RunnerCode    string           `json:"runnerCode"`
	ReadmeContent string           `json:"readmeContent"`
	Policies      []Policy         `json:"policies"`
	SetupStatus   *SetupStatusInfo `json:"setupStatus,omitempty"`
	SetupSpec     *SetupSpecInfo   `json:"setupSpec,omitempty"`
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

// MountEntry represents a host path bind-mounted into the endpoint's container
// (README.md frontmatter `container.mounts`). Only meaningful in container mode.
type MountEntry struct {
	Source   string `json:"source"`   // Host path; may contain ~ and $VAR (stored verbatim)
	Target   string `json:"target"`   // In-container path; always under /home/runner/
	ReadOnly bool   `json:"readOnly"` // Mount read-only (default true via the UI)
	IsDir    bool   `json:"isDir"`    // Whether the expanded source is a directory (for the icon)
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
	if err := validateSlug(slug); err != nil {
		return nil, err
	}
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
	if err := validateSlug(slug); err != nil {
		return "", err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	if err := validateSlug(slug); err != nil {
		return "", err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	if err := validateSlug(slug); err != nil {
		return nil, err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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

// mountHomeRoot is the only in-container location the agent handler can see:
// the in-container bwrap sandbox re-binds the runner's $HOME and nothing else,
// so a mount whose target is outside it would be invisible to the handler.
// The UI and these bindings both enforce it.
const mountHomeRoot = "/home/runner"
const mountHomePrefix = mountHomeRoot + "/"

// mountVolumesPrefix is where drag-and-drop mounts land: a fixed, predictable
// in-container location (<prefix><basename of the host path>) so the user
// never has to reason about target paths. It matches the volumes dir the
// in-container sandbox exposes to the handler.
const mountVolumesPrefix = mountHomePrefix + "volumes/"

// GetEndpointMounts returns the container bind mounts declared in an endpoint's
// README.md frontmatter. Returns an empty slice when none are declared.
func (a *App) GetEndpointMounts(slug string) ([]MountEntry, error) {
	_, fm, err := a.endpointFrontmatter(slug)
	if err != nil {
		if os.IsNotExist(err) {
			return []MountEntry{}, nil
		}
		return nil, err
	}

	mounts := mountsFromFrontmatter(fm)
	for i := range mounts {
		// Stat the exact path the SDK will mount (same expansion semantics).
		src, err := filemode.ExpandMountSource(mounts[i].Source)
		if err != nil {
			continue
		}
		if info, err := os.Stat(src); err == nil {
			mounts[i].IsDir = info.IsDir()
		}
	}
	return mounts, nil
}

// SetEndpointMount adds or updates (keyed by target) a container bind mount.
// The target is normalized under /home/runner/volumes/ (the only path the
// sandbox exposes); a bare suffix is accepted and prefixed. The source is
// stored verbatim, with the user's home dir collapsed to ~ for portability.
// Reloads the endpoint so a running container picks up the new mount.
func (a *App) SetEndpointMount(slug, source, target string, readOnly bool) error {
	src := collapseHome(strings.TrimSpace(source))
	if src == "" {
		return fmt.Errorf("mount source is required")
	}
	tgt, err := normalizeMountTarget(target)
	if err != nil {
		return err
	}
	return a.upsertEndpointMounts(slug, []MountEntry{{Source: src, Target: tgt, ReadOnly: readOnly}})
}

// AddEndpointMounts adds one read-only mount per host path, each at
// mountVolumesPrefix + <basename>. A multi-item drop in the UI lands here so
// the frontmatter is written — and the endpoint reloaded — once for the whole
// batch instead of once per item.
func (a *App) AddEndpointMounts(slug string, sources []string) error {
	entries := make([]MountEntry, 0, len(sources))
	for _, p := range sources {
		src := collapseHome(strings.TrimSpace(p))
		base := filepath.Base(strings.TrimSpace(p))
		if src == "" || base == "" || base == "." || base == string(filepath.Separator) {
			continue
		}
		// Read-only by default — the safe choice for exposing host data to an
		// agent. The user flips individual mounts to RW from the list.
		entries = append(entries, MountEntry{Source: src, Target: mountVolumesPrefix + base, ReadOnly: true})
	}
	if len(entries) == 0 {
		return fmt.Errorf("no usable mount sources given")
	}
	return a.upsertEndpointMounts(slug, entries)
}

// upsertEndpointMounts merges the given entries (keyed by target) into the
// endpoint's declared mounts, persists the frontmatter once, and reloads once.
func (a *App) upsertEndpointMounts(slug string, entries []MountEntry) error {
	err := a.mutateMounts(slug, func(mounts []MountEntry) []MountEntry {
		for _, e := range entries {
			found := false
			for i := range mounts {
				if mounts[i].Target == e.Target {
					mounts[i] = e
					found = true
					break
				}
			}
			if !found {
				mounts = append(mounts, e)
			}
		}
		return mounts
	})
	if err != nil {
		return err
	}
	if a.ctx != nil {
		for _, e := range entries {
			runtime.LogInfo(a.ctx, fmt.Sprintf("Set mount on %s: %s -> %s (read_only=%v)", slug, e.Source, e.Target, e.ReadOnly))
		}
	}
	return nil
}

// DeleteEndpointMount removes the bind mount with the given container target.
func (a *App) DeleteEndpointMount(slug, target string) error {
	tgt := strings.TrimSpace(target)
	err := a.mutateMounts(slug, func(mounts []MountEntry) []MountEntry {
		out := make([]MountEntry, 0, len(mounts))
		for _, m := range mounts {
			if m.Target != tgt {
				out = append(out, m)
			}
		}
		return out
	})
	if err != nil {
		return err
	}
	if a.ctx != nil {
		runtime.LogInfo(a.ctx, fmt.Sprintf("Deleted mount on %s: %s", slug, tgt))
	}
	return nil
}

// mutateMounts runs the read-modify-write cycle shared by every mount
// mutation: parse the frontmatter once, apply mutate to the declared mounts,
// persist, and reload the endpoint once.
func (a *App) mutateMounts(slug string, mutate func([]MountEntry) []MountEntry) error {
	readmePath, fm, err := a.endpointFrontmatter(slug)
	if err != nil {
		return err
	}
	if err := a.writeEndpointMounts(readmePath, fm, mutate(mountsFromFrontmatter(fm))); err != nil {
		return fmt.Errorf("failed to update mounts: %w", err)
	}
	a.reloadAfterEndpointMutation(slug)
	return nil
}

// endpointFrontmatter resolves an endpoint's README.md path and parses its
// frontmatter map — the shared preamble of every mount/sandbox binding.
// Callers that tolerate a missing README check os.IsNotExist on err.
func (a *App) endpointFrontmatter(slug string) (readmePath string, fm map[string]any, err error) {
	if err := validateSlug(slug); err != nil {
		return "", nil, err
	}
	config, err := a.getConfig()
	if err != nil {
		return "", nil, err
	}
	readmePath = filepath.Join(config.EndpointsPath, slug, "README.md")
	fm, err = a.loadFrontmatterMap(readmePath)
	return readmePath, fm, err
}

// loadFrontmatterMap parses a README.md's YAML frontmatter into a generic map,
// preserving every key (including container/sandbox/runtime) so callers can
// read-modify-write a single nested section without dropping the rest.
func (a *App) loadFrontmatterMap(readmePath string) (map[string]any, error) {
	f, err := os.Open(readmePath)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	yamlBytes, _, err := nodeops.SplitFrontmatter(f)
	if err != nil {
		return nil, err
	}
	fm := map[string]any{}
	if err := yaml.Unmarshal(yamlBytes, &fm); err != nil {
		return nil, fmt.Errorf("failed to parse frontmatter: %w", err)
	}
	return fm, nil
}

// frontmatterSection decodes a frontmatter sub-value into the SDK schema type
// that owns it, by round-tripping through YAML — the schema has exactly one
// owner: the SDK type the provider actually enforces. The value came from a
// YAML parse, so re-marshaling cannot fail; a wrong-typed field surfaces as a
// yaml.TypeError, which still decodes every other field — malformed entries
// degrade rather than failing the read.
func frontmatterSection[T any](v any) T {
	var out T
	if data, err := yaml.Marshal(v); err == nil {
		_ = yaml.Unmarshal(data, &out) // type errors leave the bad field zeroed
	}
	return out
}

// mountsFromFrontmatter extracts the container.mounts list from a parsed
// frontmatter map via filemode.ContainerMount (the schema owner). Always
// returns a non-nil slice so callers (and the JSON bridge) never see null.
func mountsFromFrontmatter(fm map[string]any) []MountEntry {
	out := []MountEntry{}
	container, _ := fm["container"].(map[string]any)
	if container == nil {
		return out
	}
	for _, m := range frontmatterSection[[]filemode.ContainerMount](container["mounts"]) {
		if m.Source == "" || m.Target == "" {
			continue
		}
		out = append(out, MountEntry{Source: m.Source, Target: m.Target, ReadOnly: m.ReadOnly})
	}
	return out
}

// writeEndpointMounts persists the given mounts into container.mounts (as
// filemode.ContainerMount, the schema owner), leaving any existing
// container.image (and every other frontmatter key) untouched. fm is the
// caller's already-parsed frontmatter for readmePath — passed in so a
// mutation parses the file once instead of re-reading it here.
func (a *App) writeEndpointMounts(readmePath string, fm map[string]any, mounts []MountEntry) error {
	container, _ := fm["container"].(map[string]any)
	if container == nil {
		container = map[string]any{}
	}

	list := make([]filemode.ContainerMount, 0, len(mounts))
	for _, m := range mounts {
		list = append(list, filemode.ContainerMount{Source: m.Source, Target: m.Target, ReadOnly: m.ReadOnly})
	}
	container["mounts"] = list

	return nodeops.UpdateReadmeFrontmatter(readmePath, map[string]any{"container": container})
}

// normalizeMountTarget coerces a target into a clean path under the in-container
// volumes dir (/home/runner/volumes/). A bare suffix ("work") is prefixed; an
// absolute path is validated to be under the volumes prefix and cleaned to
// defeat ../ escapes. The volumes dir is the ONLY location the in-container
// bwrap sandbox binds back over the tmpfs'd $HOME, so a target anywhere else —
// even elsewhere under /home/runner/ — would be silently invisible to the
// handler. Enforcing the volumes prefix here keeps "accepted" and "visible" the
// same set; AddEndpointMounts already targets volumes/, so it is unaffected.
func normalizeMountTarget(target string) (string, error) {
	t := strings.TrimSpace(target)
	if t == "" {
		return "", fmt.Errorf("mount target is required")
	}
	if !strings.HasPrefix(t, "/") {
		t = mountVolumesPrefix + t
	}
	clean := path.Clean(t)
	if clean == strings.TrimSuffix(mountVolumesPrefix, "/") {
		return "", fmt.Errorf("mount target cannot be %s itself", clean)
	}
	if !strings.HasPrefix(clean, mountVolumesPrefix) {
		return "", fmt.Errorf("mount target must be under %s (got %q) — only that path is visible inside the sandbox", mountVolumesPrefix, target)
	}
	return clean, nil
}

// collapseHome replaces a leading absolute home dir with ~ so stored sources
// stay portable and consistent with hand-authored frontmatter.
func collapseHome(p string) string {
	if home, err := os.UserHomeDir(); err == nil && home != "" {
		if p == home {
			return "~"
		}
		if strings.HasPrefix(p, home+string(os.PathSeparator)) {
			return "~" + p[len(home):]
		}
	}
	return p
}

// SandboxSettings is the editable view of an endpoint's README.md frontmatter
// `sandbox:` block (filemode.SandboxConfig). JSON is camelCase for the
// frontend; the on-disk YAML keys are snake_case (see writeEndpointSandbox).
// Network is intentionally absent: egress is always brokered host-side in
// container mode (see egress.go), so the runner reaches only its model API.
// NOTE: the Limits fields are persisted but not yet enforced by the runner.
type SandboxSettings struct {
	ExposeEnv       []string `json:"exposeEnv"`
	ExposeResources []string `json:"exposeResources"`
	ExposeMCP       []string `json:"exposeMcp"`      // host MCP server names this endpoint may call
	WorkspaceScope  string   `json:"workspaceScope"` // "" | "shared" | "per_user" | "per_session"
	WorkspacePath   string   `json:"workspacePath"`
	CPUCores        float64  `json:"cpuCores"`
	MemoryMB        int      `json:"memoryMb"`
	TimeoutSeconds  int      `json:"timeoutSeconds"`
	TmpfsMB         int      `json:"tmpfsMb"`
}

// GetEndpointSandbox reads the sandbox block from an endpoint's frontmatter.
// Returns zero-valued settings when no sandbox block is present.
func (a *App) GetEndpointSandbox(slug string) (*SandboxSettings, error) {
	_, fm, err := a.endpointFrontmatter(slug)
	if err != nil {
		if os.IsNotExist(err) {
			return &SandboxSettings{}, nil
		}
		return nil, err
	}
	s := sandboxFromFrontmatter(fm)
	return &s, nil
}

// SetEndpointSandbox validates and persists the sandbox block, preserving any
// unmanaged keys (e.g. workspace.quota_mb) and every sibling frontmatter key,
// then reloads the endpoint so the container rebuilds with the new isolation.
func (a *App) SetEndpointSandbox(slug string, s SandboxSettings) error {
	if err := validateSandbox(&s); err != nil {
		return err
	}
	readmePath, fm, err := a.endpointFrontmatter(slug)
	if err != nil {
		return err
	}
	if err := a.writeEndpointSandbox(readmePath, fm, s); err != nil {
		return fmt.Errorf("failed to update sandbox: %w", err)
	}

	if a.ctx != nil {
		runtime.LogInfo(a.ctx, fmt.Sprintf("Updated sandbox config for %s", slug))
	}
	a.reloadAfterEndpointMutation(slug)
	return nil
}

// validateSandbox normalizes (trim/dedupe/clamp) and validates enum fields in
// place. Returns an error for an unknown workspace scope.
func validateSandbox(s *SandboxSettings) error {
	switch s.WorkspaceScope {
	case "", "shared", "per_user", "per_session":
	default:
		return fmt.Errorf("invalid workspace scope %q", s.WorkspaceScope)
	}
	s.ExposeEnv = cleanStrings(s.ExposeEnv)
	s.ExposeResources = cleanStrings(s.ExposeResources)
	s.ExposeMCP = cleanStrings(s.ExposeMCP)
	s.WorkspacePath = strings.TrimSpace(s.WorkspacePath)
	if s.CPUCores < 0 {
		s.CPUCores = 0
	}
	if s.MemoryMB < 0 {
		s.MemoryMB = 0
	}
	if s.TimeoutSeconds < 0 {
		s.TimeoutSeconds = 0
	}
	if s.TmpfsMB < 0 {
		s.TmpfsMB = 0
	}
	return nil
}

// sandboxFromFrontmatter reads the sandbox block via filemode.SandboxConfig
// (the schema owner).
func sandboxFromFrontmatter(fm map[string]any) SandboxSettings {
	cfg := frontmatterSection[filemode.SandboxConfig](fm["sandbox"])
	return SandboxSettings{
		ExposeEnv:       cleanStrings(cfg.ExposeEnv),
		ExposeResources: cleanStrings(cfg.ExposeResources),
		ExposeMCP:       cleanStrings(cfg.ExposeMCP),
		WorkspaceScope:  cfg.Workspace.Scope,
		WorkspacePath:   cfg.Workspace.Path,
		CPUCores:        cfg.Limits.CPUCores,
		MemoryMB:        cfg.Limits.MemoryMB,
		TimeoutSeconds:  cfg.Limits.TimeoutSeconds,
		TmpfsMB:         cfg.Limits.TmpfsMB,
	}
}

// writeEndpointSandbox merges settings into the existing sandbox map (keeping
// unmanaged keys such as workspace.quota_mb) and persists it. Default/empty
// values delete their key so the frontmatter stays minimal. fm is the caller's
// already-parsed frontmatter for readmePath.
func (a *App) writeEndpointSandbox(readmePath string, fm map[string]any, s SandboxSettings) error {
	sb, _ := fm["sandbox"].(map[string]any)
	if sb == nil {
		sb = map[string]any{}
	}

	// Subprocesses are always permitted and children inherit the full env, so
	// both knobs are obsolete; strip them so the frontmatter carries no dead key.
	delete(sb, "allow_subprocess")
	delete(sb, "subprocess_env")
	putSlice(sb, "expose_env", s.ExposeEnv)
	putSlice(sb, "expose_resources", s.ExposeResources)
	putSlice(sb, "expose_mcp", s.ExposeMCP)

	ws, _ := sb["workspace"].(map[string]any)
	if ws == nil {
		ws = map[string]any{}
	}
	if s.WorkspaceScope != "" {
		ws["scope"] = s.WorkspaceScope
	} else {
		delete(ws, "scope")
	}
	if s.WorkspacePath != "" && s.WorkspacePath != "workspace" {
		ws["path"] = s.WorkspacePath
	} else {
		delete(ws, "path")
	}
	if len(ws) == 0 {
		delete(sb, "workspace")
	} else {
		sb["workspace"] = ws
	}

	lim, _ := sb["limits"].(map[string]any)
	if lim == nil {
		lim = map[string]any{}
	}
	putNum(lim, "cpu_cores", s.CPUCores)
	putNum(lim, "memory_mb", s.MemoryMB)
	putNum(lim, "timeout_seconds", s.TimeoutSeconds)
	putNum(lim, "tmpfs_mb", s.TmpfsMB)
	if len(lim) == 0 {
		delete(sb, "limits")
	} else {
		sb["limits"] = lim
	}

	return nodeops.UpdateReadmeFrontmatter(readmePath, map[string]any{"sandbox": sb})
}

func cleanStrings(in []string) []string {
	seen := make(map[string]struct{}, len(in))
	out := make([]string, 0, len(in))
	for _, v := range in {
		v = strings.TrimSpace(v)
		if v == "" {
			continue
		}
		if _, ok := seen[v]; ok {
			continue
		}
		seen[v] = struct{}{}
		out = append(out, v)
	}
	return out
}

func putSlice(m map[string]any, k string, v []string) {
	if len(v) == 0 {
		delete(m, k)
		return
	}
	arr := make([]any, len(v))
	for i, s := range v {
		arr[i] = s
	}
	m[k] = arr
}

// putNum sets m[k]=v when v is positive and deletes the key otherwise, keeping
// default/zero limits out of the persisted frontmatter.
func putNum[T int | float64](m map[string]any, k string, v T) {
	if v > 0 {
		m[k] = v
	} else {
		delete(m, k)
	}
}

// GetDependencies returns Python dependencies for an endpoint.
func (a *App) GetDependencies(slug string) ([]Dependency, error) {
	if err := validateSlug(slug); err != nil {
		return nil, err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	if err := validateSlug(slug); err != nil {
		return false, err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	// X402 carries the optional configuration the producer-UI form collects
	// for an X402PayPerRequestPolicy. When nil, generatePolicyYAML falls
	// back to sensible defaults so a bare {Name,Type} request still produces
	// a working template.
	X402 *X402PolicyConfig `json:"x402,omitempty"`
}

// X402PolicyConfig is the producer-side configuration captured by the
// X402PolicyForm in the desktop UI. All fields are optional; missing values
// fall back to the defaults applied in generatePolicyYAML so the same
// request shape can be used for both the bare new-policy modal and the
// fully-populated dedicated form.
//
// PayTo is intentionally NOT here: the producer's wallet address is
// authoritative — it comes from WalletShow() server-side, never from the
// untrusted form. Sending it client-side would let the UI direct payments
// to an arbitrary recipient.
type X402PolicyConfig struct {
	Price                         string   `json:"price,omitempty"`
	Currency                      string   `json:"currency,omitempty"`
	Decimals                      int      `json:"decimals,omitempty"`
	ChainID                       int      `json:"chainId,omitempty"`
	Realm                         string   `json:"realm,omitempty"`
	HmacSecretKid                 string   `json:"hmacSecretKid,omitempty"`
	ChallengeTTLSeconds           int      `json:"challengeTtlSeconds,omitempty"`
	MaxPendingSettlementsPerPayer int      `json:"maxPendingSettlementsPerPayer,omitempty"`
	AllowListedPayers             []string `json:"allowListedPayers,omitempty"`
}

// ListPolicyFiles returns all policy files in the endpoint's policy/ directory.
func (a *App) ListPolicyFiles(slug string) ([]PolicyFileInfo, error) {
	if err := validateSlug(slug); err != nil {
		return nil, err
	}
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

// validateSlug checks that a slug is non-empty and doesn't contain
// path-traversal characters that could escape the endpoints directory.
func validateSlug(slug string) error {
	if slug == "" {
		return fmt.Errorf("endpoint slug is required")
	}
	if strings.Contains(slug, "..") || strings.Contains(slug, "/") || strings.Contains(slug, "\\") {
		return fmt.Errorf("invalid endpoint slug")
	}
	return nil
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
	if err := validateSlug(slug); err != nil {
		return "", err
	}
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
	if err := validateSlug(slug); err != nil {
		return err
	}
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

	// Trigger reload directly so the new policy takes effect on the next
	// session/message without waiting for the file watcher's debounce. The
	// watcher would normally pick this up, but explicit reload makes the
	// behavior deterministic and matches the pattern used by setup/library.
	a.reloadAfterEndpointMutation(slug)

	return nil
}

// DeletePolicyFile removes a policy file from the endpoint's policy/ directory.
func (a *App) DeletePolicyFile(slug, filename string) error {
	if err := validateSlug(slug); err != nil {
		return err
	}
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
	a.reloadAfterEndpointMutation(slug)
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
//
// ctx is the policy-creation context: slug owning the endpoint and the
// host wallet address (when known). Both are used only by the
// X402PayPerRequestPolicy template — slug as part of the default realm
// ("syfthub:endpoint:<slug>:<policyName>") and walletAddress as the
// authoritative pay_to. Other policy templates ignore them.
type policyGenContext struct {
	slug          string
	walletAddress string
}

func generatePolicyYAML(ctx policyGenContext, req NewPolicyRequest) string {
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
		// placeholder_message is the only YAML-expressible knob ManualReviewPolicy
		// accepts (alongside name). The runner's policy factory silently drops
		// unknown config keys, so emitting anything else would be dead config.
		type manualReviewConfig struct {
			PlaceholderMessage string `yaml:"placeholder_message"`
		}
		return marshalPolicyYAML(
			"# Manual Review Policy\n# Holds endpoint responses for manual review before delivery\n",
			policyDef{Type: "ManualReviewPolicy", Name: req.Name, Config: manualReviewConfig{
				PlaceholderMessage: "Request submitted to manual review",
			}},
		)

	case "X402PayPerRequestPolicy":
		// pay_to is sourced from the host wallet (ctx.walletAddress) — never
		// from the request — so a producer cannot misroute payments via the
		// UI. The rest of the knobs come from the X402PolicyForm; missing
		// values fall back to demo-network defaults.
		type x402Config struct {
			PayTo                         string   `yaml:"pay_to"`
			Price                         string   `yaml:"price"`
			Currency                      string   `yaml:"currency"`
			Decimals                      int      `yaml:"decimals"`
			ChainID                       int      `yaml:"chain_id"`
			Realm                         string   `yaml:"realm"`
			HmacSecretKid                 string   `yaml:"hmac_secret_kid"`
			ChallengeTTLSeconds           int      `yaml:"challenge_ttl_seconds"`
			MaxPendingSettlementsPerPayer int      `yaml:"max_pending_settlements_per_payer"`
			AllowListedPayers             []string `yaml:"allow_listed_payers,omitempty"`
		}
		cfg := x402Config{
			PayTo:                         ctx.walletAddress,
			Price:                         "0.01",
			Currency:                      pathUSDContractAddress,
			Decimals:                      pathUSDDecimals,
			ChainID:                       int(defaultChainID),
			Realm:                         defaultX402Realm(ctx.slug, req.Name),
			HmacSecretKid:                 "default",
			ChallengeTTLSeconds:           300,
			MaxPendingSettlementsPerPayer: 16,
			AllowListedPayers:             nil,
		}
		if req.X402 != nil {
			form := req.X402
			if strings.TrimSpace(form.Price) != "" {
				cfg.Price = form.Price
			}
			if strings.TrimSpace(form.Currency) != "" {
				cfg.Currency = form.Currency
			}
			if form.Decimals > 0 {
				cfg.Decimals = form.Decimals
			}
			if form.ChainID > 0 {
				cfg.ChainID = form.ChainID
			}
			if strings.TrimSpace(form.Realm) != "" {
				cfg.Realm = form.Realm
			}
			if strings.TrimSpace(form.HmacSecretKid) != "" {
				cfg.HmacSecretKid = form.HmacSecretKid
			}
			if form.ChallengeTTLSeconds > 0 {
				cfg.ChallengeTTLSeconds = form.ChallengeTTLSeconds
			}
			if form.MaxPendingSettlementsPerPayer > 0 {
				cfg.MaxPendingSettlementsPerPayer = form.MaxPendingSettlementsPerPayer
			}
			if len(form.AllowListedPayers) > 0 {
				cfg.AllowListedPayers = form.AllowListedPayers
			}
		}
		return marshalPolicyYAML(
			"# X402 Pay-Per-Request Policy\n# Gates access behind on-chain Tempo (pathUSD) payment\n",
			policyDef{Type: "X402PayPerRequestPolicy", Name: req.Name, Config: cfg},
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

// defaultX402Realm builds the default realm string the X402 policy template
// emits when the form doesn't override it. The convention pins the realm
// to a specific (slug, policy_name) pair so two policies on different
// endpoints never collide on the producer's HMAC keystore.
func defaultX402Realm(slug, policyName string) string {
	if slug == "" {
		return fmt.Sprintf("syfthub:endpoint:%s", policyName)
	}
	return fmt.Sprintf("syfthub:endpoint:%s:%s", slug, policyName)
}

// CreatePolicyFile creates a new policy file with a template based on the request.
func (a *App) CreatePolicyFile(slug string, req NewPolicyRequest) error {
	if err := validateSlug(slug); err != nil {
		return err
	}
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

	// Generate template content based on policy type. X402 templates need the
	// producer's wallet address to populate pay_to authoritatively; we look
	// it up here rather than trusting the request payload. Missing-wallet
	// failures are non-fatal — the YAML is still emitted with an empty
	// pay_to so the operator can either edit it directly or initialise the
	// wallet and recreate the policy.
	ctx := policyGenContext{slug: slug}
	if info, infoErr := a.WalletShow(); infoErr == nil {
		ctx.walletAddress = info.Address
	} else if a.ctx != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("CreatePolicyFile: wallet lookup failed (slug=%s): %v", slug, infoErr))
	}
	content := generatePolicyYAML(ctx, req)

	if err := os.WriteFile(policyPath, []byte(content), 0644); err != nil {
		return fmt.Errorf("failed to create policy file: %w", err)
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Created policy file '%s' (type: %s) for endpoint: %s", filename, req.Type, slug))
	a.reloadAfterEndpointMutation(slug)
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
// After removing from disk, the endpoint is immediately purged from the in-memory
// provider, registry, and frontend so no "ghost" can reappear.
func (a *App) DeleteEndpoint(slug string) error {
	a.mu.RLock()
	if a.config == nil {
		a.mu.RUnlock()
		return fmt.Errorf("app not configured")
	}
	endpointsPath := a.config.EndpointsPath
	core := a.core
	a.mu.RUnlock()

	mgr := nodeops.NewManager(endpointsPath)
	if err := mgr.DeleteEndpoint(slug); err != nil {
		return err
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Deleted endpoint: %s", slug))

	// Synchronously remove from provider (p.endpoints + executor) and registry
	// so the endpoint vanishes from GetEndpoints() right now — no waiting for
	// the debounced file watcher.
	if core != nil {
		core.RemoveEndpoint(slug)
		// Propagate the deletion to SyftHub. The /endpoints/sync POST is
		// authoritative — endpoints absent from the posted list are deleted
		// hub-side — so this is what removes the endpoint from the web UI.
		core.SyncEndpointsAsync()
	}
	a.notifyEndpointsChanged()
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

// RenameEndpoint changes an endpoint's folder name (its slug).
//
// The slug is the endpoint's identity: the on-disk directory name, the `slug`
// field in README.md frontmatter, and the key the hub stores the endpoint
// under. This renames the directory, realigns the frontmatter slug (and the
// pyproject.toml project name), then reloads so the in-memory registry and the
// hub pick up the change.
//
// The hub keys endpoints by slug and has no slug-preserving update, so this
// lands hub-side as a delete of the old slug plus a create of the new one —
// the public URL /{owner}/{slug} changes accordingly.
//
// newName is run through the same slugify rules as CreateEndpoint; the
// resulting slug is returned.
func (a *App) RenameEndpoint(oldSlug, newName string) (string, error) {
	if err := validateSlug(oldSlug); err != nil {
		return "", err
	}

	newSlug := nodeops.Slugify(newName)
	if newSlug == "" {
		return "", fmt.Errorf("could not generate a valid folder name from %q", newName)
	}
	if newSlug == oldSlug {
		return "", fmt.Errorf("endpoint folder is already named %q", newSlug)
	}

	config, err := a.getConfig()
	if err != nil {
		return "", err
	}

	oldDir := filepath.Join(config.EndpointsPath, oldSlug)
	newDir := filepath.Join(config.EndpointsPath, newSlug)

	if _, err := os.Stat(oldDir); err != nil {
		return "", fmt.Errorf("endpoint %q not found", oldSlug)
	}
	if _, err := os.Stat(newDir); !os.IsNotExist(err) {
		return "", fmt.Errorf("an endpoint folder named %q already exists", newSlug)
	}

	// Rename the directory on disk.
	if err := os.Rename(oldDir, newDir); err != nil {
		return "", fmt.Errorf("failed to rename endpoint folder: %w", err)
	}

	// Keep the README.md frontmatter slug consistent with the directory name.
	// The SDK loader trusts the frontmatter slug, so a mismatch would desync
	// the endpoint's in-memory identity from its folder. Roll the directory
	// rename back if the frontmatter update fails.
	readmePath := filepath.Join(newDir, "README.md")
	if err := nodeops.UpdateReadmeFrontmatter(readmePath, map[string]interface{}{"slug": newSlug}); err != nil {
		if rbErr := os.Rename(newDir, oldDir); rbErr != nil {
			runtime.LogError(a.ctx, fmt.Sprintf("Rename rollback failed (%s -> %s): %v", newSlug, oldSlug, rbErr))
		}
		return "", fmt.Errorf("failed to update README.md frontmatter: %w", err)
	}

	// Best-effort: realign pyproject.toml [project].name (CreateEndpoint sets
	// it to the slug). Not fatal — it is cosmetic and unrelated to identity.
	a.realignPyprojectName(filepath.Join(newDir, "pyproject.toml"), newSlug)

	runtime.LogInfo(a.ctx, fmt.Sprintf("Renamed endpoint %q -> %q", oldSlug, newSlug))

	// Drop transient UI lifecycle state tracked under the old slug.
	a.clearRuntimeState(oldSlug)

	// Reload from disk so the registry drops the old slug, loads the new one,
	// and re-syncs with the hub. ReloadEndpoints reconciles the whole set
	// against the filesystem, so the stale old-slug executor is closed too.
	a.reloadAfterEndpointMutation(newSlug)

	return newSlug, nil
}

// realignPyprojectName best-effort rewrites the [project].name field in an
// endpoint's pyproject.toml after a folder rename. Failures are logged, not
// returned: the project name is cosmetic and unrelated to endpoint identity.
func (a *App) realignPyprojectName(path, newName string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return // no pyproject.toml, or unreadable — nothing to realign
	}
	lines := strings.Split(string(data), "\n")
	inProject := false
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "[") {
			inProject = trimmed == "[project]"
			continue
		}
		if inProject && strings.HasPrefix(trimmed, "name") && strings.Contains(trimmed, "=") {
			lines[i] = fmt.Sprintf("name = %q", newName)
			if err := os.WriteFile(path, []byte(strings.Join(lines, "\n")), 0644); err != nil {
				runtime.LogWarning(a.ctx, fmt.Sprintf("Failed to realign pyproject.toml name: %v", err))
			}
			return
		}
	}
}

// ============================================================================
// Skills bindings
//
// Agent endpoints load runtime knowledge from
//   <endpointDir>/skills/<name>/SKILL.md (+ optional sibling files)
// These bindings let the desktop UI install a skill from a single SKILL.md
// drop or from a whole folder drag-drop, list installed skills, preview their
// markdown, and remove them.
// ============================================================================

// SkillInfo is the JSON shape returned to the frontend for a single installed skill.
type SkillInfo struct {
	Name       string `json:"name"`
	Title      string `json:"title"`
	Size       int64  `json:"size"`
	ModifiedAt string `json:"modifiedAt"`
}

// maxSkillFileBytes caps the size of any individual file copied into a skill
// directory. A typical SKILL.md is ~5KB; the cap is generous enough for
// scripts/data but prevents an accidental drop of a huge file.
const maxSkillFileBytes = 5 * 1024 * 1024 // 5 MiB

// maxSkillBundleFiles caps the number of files copied per bundle so a
// pathological folder drop can't fan out unbounded.
const maxSkillBundleFiles = 256

// skillNameFromRawRe is the same regex Go-side ValidateSkillName uses; we
// match against it here for the slugifier rather than re-importing nodeops.
var skillSlugReplaceRe = regexp.MustCompile(`[^a-z0-9_-]+`)

// ListSkills returns every installed skill for an endpoint, sorted by name.
func (a *App) ListSkills(slug string) ([]SkillInfo, error) {
	if err := validateSlug(slug); err != nil {
		return nil, err
	}
	endpointDir, err := a.skillEndpointDir(slug)
	if err != nil {
		return nil, err
	}
	skills, err := nodeops.ListSkills(endpointDir)
	if err != nil {
		return nil, err
	}
	out := make([]SkillInfo, len(skills))
	for i, s := range skills {
		out[i] = SkillInfo{
			Name:       s.Name,
			Title:      s.Title,
			Size:       s.Size,
			ModifiedAt: s.ModifiedAt.UTC().Format(time.RFC3339Nano),
		}
	}
	return out, nil
}

// ReadSkill returns the SKILL.md body for an installed skill.
func (a *App) ReadSkill(slug, name string) (string, error) {
	if err := validateSlug(slug); err != nil {
		return "", err
	}
	endpointDir, err := a.skillEndpointDir(slug)
	if err != nil {
		return "", err
	}
	return nodeops.ReadSkill(endpointDir, name)
}

// RemoveSkill deletes <endpointDir>/skills/<name>/ recursively.
func (a *App) RemoveSkill(slug, name string) error {
	if err := validateSlug(slug); err != nil {
		return err
	}
	endpointDir, err := a.skillEndpointDir(slug)
	if err != nil {
		return err
	}
	if err := nodeops.RemoveSkill(endpointDir, name); err != nil {
		return err
	}
	runtime.EventsEmit(a.ctx, "app:endpoints-changed", nil)
	return nil
}

// InstallSkillFromPaths installs a skill from one or more absolute paths
// delivered by Wails' native file drop (or a native file dialog). It
// auto-detects the kind of drop:
//
//   - exactly one path → a directory: copy the folder contents into
//     <endpoint>/skills/<slugified-folder-name>/. SKILL.md must exist at the root.
//   - exactly one path → a regular file ending in .md (case-insensitive): treat
//     it as a SKILL.md drop. The skill name is derived from the file's parent
//     directory if its basename is literally SKILL.md, else from the file's
//     basename (without extension).
//   - anything else (multiple paths, non-.md file, etc.) → return an error.
//
// All copies are size-capped (maxSkillFileBytes per file) and count-capped
// (maxSkillBundleFiles per bundle), and the destination directory is created
// fresh so reinstalling a skill replaces it cleanly.
func (a *App) InstallSkillFromPaths(slug string, paths []string) error {
	if err := validateSlug(slug); err != nil {
		return err
	}
	endpointDir, err := a.skillEndpointDir(slug)
	if err != nil {
		return err
	}
	if len(paths) == 0 {
		return fmt.Errorf("no files dropped")
	}
	if len(paths) > 1 {
		return fmt.Errorf("drop one folder or one SKILL.md file at a time (got %d)", len(paths))
	}

	src := paths[0]
	st, err := os.Stat(src)
	if err != nil {
		return fmt.Errorf("cannot read %s: %w", filepath.Base(src), err)
	}

	if st.IsDir() {
		return a.installSkillFromDir(endpointDir, src)
	}
	return a.installSkillFromFile(endpointDir, src)
}

// installSkillFromFile handles the single-SKILL.md drop case.
func (a *App) installSkillFromFile(endpointDir, src string) error {
	if !strings.HasSuffix(strings.ToLower(src), ".md") {
		return fmt.Errorf("only .md files are supported (got %s)", filepath.Base(src))
	}
	st, err := os.Stat(src)
	if err != nil {
		return err
	}
	if st.Size() > maxSkillFileBytes {
		return fmt.Errorf("file exceeds %d bytes", maxSkillFileBytes)
	}

	// Derive the skill name. If the user dropped a file literally named
	// SKILL.md (any case), use its parent directory's name as the slug —
	// that's almost certainly what they intended. Otherwise use the file's
	// basename without extension.
	base := filepath.Base(src)
	var rawName string
	if strings.EqualFold(base, nodeops.SkillFileName) {
		rawName = filepath.Base(filepath.Dir(src))
	} else {
		rawName = strings.TrimSuffix(base, filepath.Ext(base))
	}
	name := slugifySkillName(rawName)
	if err := nodeops.ValidateSkillName(name); err != nil {
		return fmt.Errorf("derived skill name %q is invalid: %w", name, err)
	}

	body, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	if err := nodeops.WriteSkill(endpointDir, name, string(body)); err != nil {
		return err
	}
	runtime.EventsEmit(a.ctx, "app:endpoints-changed", nil)
	return nil
}

// installSkillFromDir handles the folder-drop case. The folder must contain
// SKILL.md at its top level. The destination directory is wiped first so a
// reinstall doesn't leave orphaned files.
func (a *App) installSkillFromDir(endpointDir, srcDir string) error {
	rawName := filepath.Base(srcDir)
	name := slugifySkillName(rawName)
	if err := nodeops.ValidateSkillName(name); err != nil {
		return fmt.Errorf("derived skill name %q is invalid: %w", name, err)
	}

	// Find SKILL.md at the top level (case-insensitive) and read it first
	// so we can route the install through nodeops.WriteSkill (which creates
	// the dir, validates, and touches .env to fire the file watcher).
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return fmt.Errorf("read %s: %w", filepath.Base(srcDir), err)
	}
	var skillMdPath string
	for _, e := range entries {
		if !e.IsDir() && strings.EqualFold(e.Name(), nodeops.SkillFileName) {
			skillMdPath = filepath.Join(srcDir, e.Name())
			break
		}
	}
	if skillMdPath == "" {
		return fmt.Errorf("folder is missing %s at the top level", nodeops.SkillFileName)
	}

	skillMdInfo, err := os.Stat(skillMdPath)
	if err != nil {
		return err
	}
	if skillMdInfo.Size() > maxSkillFileBytes {
		return fmt.Errorf("%s exceeds %d bytes", nodeops.SkillFileName, maxSkillFileBytes)
	}
	skillMdBody, err := os.ReadFile(skillMdPath)
	if err != nil {
		return err
	}

	// Wipe any existing skill dir so re-installing replaces cleanly.
	destDir := filepath.Join(endpointDir, nodeops.SkillsDirName, name)
	if err := os.RemoveAll(destDir); err != nil {
		return fmt.Errorf("clean target: %w", err)
	}

	// Write SKILL.md via nodeops (creates dir, fires watcher).
	if err := nodeops.WriteSkill(endpointDir, name, string(skillMdBody)); err != nil {
		return err
	}

	// Copy the rest. We re-resolve destDir defensively in case nodeops
	// changed any naming semantics. Walk srcDir, skipping hidden entries
	// and the already-copied SKILL.md at the root.
	fileCount := 1 // SKILL.md already written
	err = filepath.Walk(srcDir, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == srcDir {
			return nil
		}
		rel, err := filepath.Rel(srcDir, path)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)

		// Skip hidden files/dirs and common build artifacts at any depth.
		if shouldSkipSkillFile(rel) {
			if info.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		// Skip the already-copied SKILL.md at the root.
		if !info.IsDir() && strings.EqualFold(rel, nodeops.SkillFileName) {
			return nil
		}

		target := filepath.Join(destDir, filepath.FromSlash(rel))
		if info.IsDir() {
			return os.MkdirAll(target, 0755)
		}
		if !info.Mode().IsRegular() {
			return nil // skip symlinks, sockets, etc.
		}
		if info.Size() > maxSkillFileBytes {
			return fmt.Errorf("%s exceeds %d bytes", rel, maxSkillFileBytes)
		}
		fileCount++
		if fileCount > maxSkillBundleFiles {
			return fmt.Errorf("bundle has more than %d files", maxSkillBundleFiles)
		}
		return copyFileTo(path, target)
	})
	if err != nil {
		// Roll back partial copy by removing the destination directory.
		_ = os.RemoveAll(destDir)
		return err
	}

	runtime.EventsEmit(a.ctx, "app:endpoints-changed", nil)
	return nil
}

// BrowseForSkillFile opens a native file picker filtered to .md files and
// returns the absolute path, or an empty string if the user cancelled.
func (a *App) BrowseForSkillFile(title string) string {
	if title == "" {
		title = "Choose SKILL.md"
	}
	path, err := runtime.OpenFileDialog(a.ctx, runtime.OpenDialogOptions{
		Title: title,
		Filters: []runtime.FileFilter{
			{DisplayName: "Markdown files (*.md)", Pattern: "*.md"},
		},
	})
	if err != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("Skill file dialog error: %v", err))
		return ""
	}
	return path
}

// skillEndpointDir returns the absolute path of the endpoint directory and
// verifies it exists.
func (a *App) skillEndpointDir(slug string) (string, error) {
	cfg, err := a.getConfig()
	if err != nil {
		return "", err
	}
	dir := filepath.Join(cfg.EndpointsPath, slug)
	st, err := os.Stat(dir)
	if err != nil {
		return "", fmt.Errorf("endpoint not found: %s", slug)
	}
	if !st.IsDir() {
		return "", fmt.Errorf("endpoint path is not a directory: %s", slug)
	}
	return dir, nil
}

// slugifySkillName normalizes raw text to the lowercase ^[a-z0-9][a-z0-9_-]{0,63}$
// shape enforced by nodeops.ValidateSkillName.
func slugifySkillName(raw string) string {
	s := strings.ToLower(strings.TrimSpace(raw))
	s = strings.TrimSuffix(s, ".md")
	s = strings.TrimSuffix(s, ".markdown")
	s = skillSlugReplaceRe.ReplaceAllString(s, "-")
	s = strings.Trim(s, "-")
	if len(s) > 64 {
		s = s[:64]
	}
	if s == "" {
		s = "skill"
	}
	// Leading char must be alnum; insert a placeholder if it isn't.
	if !((s[0] >= 'a' && s[0] <= 'z') || (s[0] >= '0' && s[0] <= '9')) {
		s = "s" + s
		if len(s) > 64 {
			s = s[:64]
		}
	}
	return s
}

// shouldSkipSkillFile returns true for paths that should never be copied
// into a skill bundle: hidden files/dirs, VCS metadata, and common build
// artifacts. The check is applied to each segment so a hidden parent skips
// the whole subtree.
func shouldSkipSkillFile(rel string) bool {
	for seg := range strings.SplitSeq(rel, "/") {
		if seg == "" {
			continue
		}
		if strings.HasPrefix(seg, ".") {
			return true
		}
		switch seg {
		case "node_modules", "__pycache__", "dist", "build":
			return true
		}
	}
	return false
}

// copyFileTo copies src to dst with maxSkillFileBytes capacity protection.
// Parent directories of dst are created as needed.
func copyFileTo(src, dst string) error {
	if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
		return err
	}
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
	if err != nil {
		return err
	}
	// LimitReader guards against the (unlikely) race where the file grows
	// between stat and copy past our cap.
	if _, err := io.Copy(out, io.LimitReader(in, maxSkillFileBytes+1)); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

// ============================================================================
// X402 receipts (producer-side ledger)
//
// The Python X402PayPerRequestPolicy writes its settlement ledger to the
// endpoint's shared policy store (the same SQLite file ManualReviewPolicy
// uses). The desktop UI surfaces those rows so a producer can audit who
// has paid for access. The schema is documented in
// policy_manager/policies/x402_pay_per_request.py.
// ============================================================================

// X402Receipt is one row of the producer's x402_transactions ledger,
// formatted for the frontend. Field order/casing matches the snake_case
// the rest of the Wails JSON payloads use.
type X402Receipt struct {
	ID            string `json:"id"`
	Payer         string `json:"payer"`
	PayTo         string `json:"pay_to"`
	Amount        string `json:"amount"`
	Currency      string `json:"currency"`
	ChainID       uint64 `json:"chain_id"`
	Nonce         int64  `json:"nonce"`
	ChallengeID   string `json:"challenge_id"`
	Status        string `json:"status"`
	FailureReason string `json:"failure_reason,omitempty"`
	TxHash        string `json:"tx_hash,omitempty"`
	CreatedAt     string `json:"created_at"`
	SettledAt     string `json:"settled_at,omitempty"`
}

// X402ReceiptFilter narrows a GetPolicyReceipts query. Empty Status / Payer
// disable the corresponding clause. Limit clamps to [1, maxX402Receipts];
// 0 (the JSON zero value) falls back to defaultX402Receipts so the
// frontend can omit the field for the common "first page" case.
type X402ReceiptFilter struct {
	Status string `json:"status,omitempty"`
	Payer  string `json:"payer,omitempty"`
	Limit  int    `json:"limit,omitempty"`
}

// X402ReceiptPage is the paginated result returned to the frontend. Total
// is the full count for the (slug, policy, filter) combination, regardless
// of Limit — handy for showing "showing 50 of 1234" in the UI.
type X402ReceiptPage struct {
	Records []X402Receipt `json:"records"`
	Total   int           `json:"total"`
}

const (
	defaultX402Receipts = 50
	maxX402Receipts     = 500
)

// x402TableExists returns true when the x402_transactions table has been
// created in the given pool. Mirrors manualReviewsTableExists so a fresh
// endpoint (no payments yet) returns an empty page instead of erroring.
func x402TableExists(db *sql.DB) bool {
	var name string
	err := db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='table' AND name='x402_transactions'",
	).Scan(&name)
	return err == nil && name == "x402_transactions"
}

// GetPolicyReceipts returns one page of the producer-side x402 ledger
// scoped to (slug, policyName). Reads the shared policy store
// (<endpointDir>/policy/store.db) directly — the Python policy uses WAL +
// busy_timeout=5000, which lets external readers coexist with the runner.
//
// A missing store file, or a present store with no x402_transactions
// table yet, returns an empty page rather than an error: "no payments
// yet" is a normal first-launch state, not a fault.
func (a *App) GetPolicyReceipts(slug, policyName string, filter X402ReceiptFilter) (X402ReceiptPage, error) {
	page := X402ReceiptPage{Records: []X402Receipt{}}
	if err := validateSlug(slug); err != nil {
		return page, err
	}
	if strings.TrimSpace(policyName) == "" {
		return page, fmt.Errorf("policy name is required")
	}
	config, err := a.getConfig()
	if err != nil {
		return page, err
	}

	limit := filter.Limit
	if limit <= 0 {
		limit = defaultX402Receipts
	}
	if limit > maxX402Receipts {
		limit = maxX402Receipts
	}

	dbPath := reviewStoreDBPath(config.EndpointsPath, slug)
	if _, err := os.Stat(dbPath); err != nil {
		if os.IsNotExist(err) {
			return page, nil
		}
		return page, fmt.Errorf("failed to stat policy store: %w", err)
	}

	db, err := a.routingDB(dbPath)
	if err != nil {
		return page, fmt.Errorf("failed to open policy store: %w", err)
	}

	if !x402TableExists(db) {
		return page, nil
	}

	clauses := []string{"policy_name = ?"}
	args := []any{policyName}
	if s := strings.TrimSpace(filter.Status); s != "" {
		clauses = append(clauses, "status = ?")
		args = append(args, s)
	}
	if p := strings.TrimSpace(filter.Payer); p != "" {
		clauses = append(clauses, "payer = ?")
		args = append(args, p)
	}
	where := strings.Join(clauses, " AND ")

	// Total first — independent of limit so the UI can show "n of N".
	var total int
	if err := db.QueryRow(
		"SELECT COUNT(*) FROM x402_transactions WHERE "+where,
		args...,
	).Scan(&total); err != nil {
		return page, fmt.Errorf("failed to count receipts: %w", err)
	}
	page.Total = total

	rowArgs := make([]any, 0, len(args)+1)
	rowArgs = append(rowArgs, args...)
	rowArgs = append(rowArgs, limit)
	rows, err := db.Query(
		"SELECT id, payer, pay_to, amount, currency, chain_id, "+
			"nonce, status, failure_reason, tx_hash, "+
			"created_at, settled_at "+
			"FROM x402_transactions WHERE "+where+
			" ORDER BY created_at DESC LIMIT ?",
		rowArgs...,
	)
	if err != nil {
		return page, fmt.Errorf("failed to query receipts: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var (
			rec           X402Receipt
			nonce         sql.NullInt64
			failureReason sql.NullString
			txHash        sql.NullString
			settledAt     sql.NullString
		)
		if err := rows.Scan(
			&rec.ID,
			&rec.Payer,
			&rec.PayTo,
			&rec.Amount,
			&rec.Currency,
			&rec.ChainID,
			&nonce,
			&rec.Status,
			&failureReason,
			&txHash,
			&rec.CreatedAt,
			&settledAt,
		); err != nil {
			if a.ctx != nil {
				runtime.LogWarning(a.ctx, fmt.Sprintf("GetPolicyReceipts: skipping unreadable row: %v", err))
			}
			continue
		}
		rec.ChallengeID = rec.ID
		if nonce.Valid {
			rec.Nonce = nonce.Int64
		}
		if failureReason.Valid {
			rec.FailureReason = failureReason.String
		}
		if txHash.Valid {
			rec.TxHash = txHash.String
		}
		if settledAt.Valid {
			rec.SettledAt = settledAt.String
		}
		page.Records = append(page.Records, rec)
	}
	if err := rows.Err(); err != nil {
		return page, fmt.Errorf("failed to read receipts: %w", err)
	}
	return page, nil
}
