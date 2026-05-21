package filemode

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeLoaded returns a *LoadedEndpoint that points at an endpoint directory
// laid out exactly like a real one. The test driver writes the files it
// wants to exist; this helper only fills out the *LoadedEndpoint struct.
func fakeLoaded(t *testing.T, dir string, sandbox SandboxConfig) *LoadedEndpoint {
	t.Helper()
	return &LoadedEndpoint{
		Config: &EndpointConfig{
			Slug:    "ep",
			Type:    "agent",
			Name:    "ep",
			Sandbox: sandbox,
		},
		Dir:        dir,
		RunnerPath: filepath.Join(dir, "runner.py"),
	}
}

func mustWrite(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestBuildSandboxManifest_ExcludesSecrets(t *testing.T) {
	dir := t.TempDir()
	mustWrite(t, filepath.Join(dir, "runner.py"), "def handler(s): pass")
	mustWrite(t, filepath.Join(dir, "helper.py"), "x = 1")
	mustWrite(t, filepath.Join(dir, ".env"), "API_KEY=secret")
	mustWrite(t, filepath.Join(dir, "policy", "rate.yaml"), "name: rate")
	mustWrite(t, filepath.Join(dir, "setup.yaml"), "steps: []")
	mustWrite(t, filepath.Join(dir, ".setup-state.json"), "{}")
	mustWrite(t, filepath.Join(dir, "policies.yaml"), "policies: []")

	m, err := BuildSandboxManifest(fakeLoaded(t, dir, SandboxConfig{}))
	if err != nil {
		t.Fatal(err)
	}

	// runner.py + helper.py present.
	codeSet := map[string]bool{}
	for _, c := range m.CodePaths {
		codeSet[c] = true
	}
	if !codeSet["runner.py"] || !codeSet["helper.py"] {
		t.Errorf("expected runner.py + helper.py, got %v", m.CodePaths)
	}

	// No secret files in the manifest.
	for _, c := range m.CodePaths {
		if isSecretFile(c) {
			t.Errorf("secret leaked into manifest: %q", c)
		}
	}
}

func TestBuildSandboxManifest_ExposeResources(t *testing.T) {
	dir := t.TempDir()
	mustWrite(t, filepath.Join(dir, "runner.py"), "")
	mustWrite(t, filepath.Join(dir, "prompts", "system.txt"), "hi")

	m, err := BuildSandboxManifest(fakeLoaded(t, dir, SandboxConfig{
		ExposeResources: []string{"prompts/"},
	}))
	if err != nil {
		t.Fatal(err)
	}
	if len(m.ResourcePaths) != 1 || m.ResourcePaths[0] != "prompts" {
		t.Errorf("expected ResourcePaths=[prompts], got %v", m.ResourcePaths)
	}
}

func TestBuildSandboxManifest_RejectsSecretAsResource(t *testing.T) {
	dir := t.TempDir()
	mustWrite(t, filepath.Join(dir, "runner.py"), "")
	mustWrite(t, filepath.Join(dir, ".env"), "X=1")

	cases := []string{".env", "policy/", "setup.yaml", ".setup-state.json", "policies.yaml"}
	for _, tc := range cases {
		_, err := BuildSandboxManifest(fakeLoaded(t, dir, SandboxConfig{
			ExposeResources: []string{tc},
		}))
		if err == nil {
			t.Errorf("expected error for expose_resources=%q", tc)
		}
	}
}

func TestBuildSandboxManifest_RejectsTraversal(t *testing.T) {
	dir := t.TempDir()
	mustWrite(t, filepath.Join(dir, "runner.py"), "")

	_, err := BuildSandboxManifest(fakeLoaded(t, dir, SandboxConfig{
		ExposeResources: []string{"../secrets"},
	}))
	if err == nil {
		t.Error("expected error for ../ traversal")
	}

	_, err = BuildSandboxManifest(fakeLoaded(t, dir, SandboxConfig{
		ExposeResources: []string{"/etc/passwd"},
	}))
	if err == nil {
		t.Error("expected error for absolute path")
	}
}

func TestMaterializeSandbox_NoSecretsInDest(t *testing.T) {
	src := t.TempDir()
	dest := filepath.Join(t.TempDir(), "synth")

	mustWrite(t, filepath.Join(src, "runner.py"), "def handler(s): pass")
	mustWrite(t, filepath.Join(src, "helper.py"), "y = 2")
	mustWrite(t, filepath.Join(src, ".env"), "API_KEY=hunter2")
	mustWrite(t, filepath.Join(src, "policy", "rate.yaml"), "name: rate")
	mustWrite(t, filepath.Join(src, "setup.yaml"), "steps: []")
	mustWrite(t, filepath.Join(src, "pyproject.toml"), "[project]\nname='ep'")

	m, err := BuildSandboxManifest(fakeLoaded(t, src, SandboxConfig{}))
	if err != nil {
		t.Fatal(err)
	}
	if err := MaterializeSandbox(m, dest, nil); err != nil {
		t.Fatal(err)
	}

	// Walk dest and assert no secret names appear anywhere.
	_ = filepath.Walk(dest, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(dest, p)
		if isSecretFile(rel) {
			t.Errorf("secret %q materialized into synth dir", rel)
		}
		return nil
	})

	// Code files must be present.
	for _, want := range []string{"runner.py", "helper.py", "pyproject.toml"} {
		if _, err := os.Stat(filepath.Join(dest, want)); err != nil {
			t.Errorf("expected %q in synth dir: %v", want, err)
		}
	}
}

func TestMaterializeSandbox_RejectsSymlinkEscape(t *testing.T) {
	src := t.TempDir()
	outside := t.TempDir() // separate dir; symlink targets it
	mustWrite(t, filepath.Join(src, "runner.py"), "")
	mustWrite(t, filepath.Join(outside, "secret"), "leak")

	// Symlink under expose_resources that escapes the endpoint root.
	if err := os.Symlink(filepath.Join(outside, "secret"),
		filepath.Join(src, "linkout")); err != nil {
		t.Skipf("symlink not supported on this filesystem: %v", err)
	}

	m, err := BuildSandboxManifest(fakeLoaded(t, src, SandboxConfig{
		ExposeResources: []string{"linkout"},
	}))
	if err != nil {
		t.Fatal(err)
	}

	dest := filepath.Join(t.TempDir(), "synth")
	err = MaterializeSandbox(m, dest, nil)
	if err == nil {
		t.Fatal("expected symlink-escape error")
	}
	if !strings.Contains(err.Error(), "escape") {
		t.Errorf("expected 'escape' in error: %v", err)
	}
}

func TestMaterializeSandbox_HardlinkOrCopy(t *testing.T) {
	src := t.TempDir()
	dest := filepath.Join(t.TempDir(), "synth")
	mustWrite(t, filepath.Join(src, "runner.py"), "code")

	m, err := BuildSandboxManifest(fakeLoaded(t, src, SandboxConfig{}))
	if err != nil {
		t.Fatal(err)
	}
	if err := MaterializeSandbox(m, dest, nil); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(dest, "runner.py"))
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "code" {
		t.Errorf("materialized content = %q, want %q", string(data), "code")
	}
}

func TestSplitEnvForSandbox(t *testing.T) {
	envVars := []string{"OPENAI_API_KEY=sk-x", "BILLING_TOKEN=tok", "LOG_LEVEL=INFO"}

	// Explicit allowlist via sandbox.expose_env narrows the handler view.
	sb := &SandboxConfig{ExposeEnv: []string{"OPENAI_API_KEY"}}
	handler, policy := splitEnvForSandbox(envVars, sb)
	if len(handler) != 1 || handler[0] != "OPENAI_API_KEY=sk-x" {
		t.Errorf("expose_env allowlist failed: handler=%v", handler)
	}
	if len(policy) != 3 {
		t.Errorf("policy env should retain all vars: %v", policy)
	}

	// Default (no expose_env): handler sees the full .env. This matches
	// pre-sandbox behavior — most endpoints put things in .env precisely
	// because the handler needs them.
	handler, _ = splitEnvForSandbox(envVars, &SandboxConfig{})
	got := map[string]bool{}
	for _, kv := range handler {
		got[kv] = true
	}
	for _, want := range []string{
		"OPENAI_API_KEY=sk-x",
		"BILLING_TOKEN=tok",
		"LOG_LEVEL=INFO",
	} {
		if !got[want] {
			t.Errorf("default should expose %q to handler; got %v", want, handler)
		}
	}

	// nil SandboxConfig is equivalent to "no expose_env" — expose all.
	handler, _ = splitEnvForSandbox(envVars, nil)
	if len(handler) != 3 {
		t.Errorf("nil sandbox config: expected full env, got %v", handler)
	}
}

func TestIsSecretFile(t *testing.T) {
	cases := []struct {
		path  string
		want  bool
		label string
	}{
		{".env", true, "top-level .env"},
		{"setup.yaml", true, "setup.yaml"},
		{".setup-state.json", true, "state file"},
		{"policy/rate.yaml", true, "policy subdir"},
		{"policy", true, "policy dir itself"},
		{"policies.yaml", true, "legacy top-level policies"},
		{"runner.py", false, "code"},
		{"helper.py", false, "code"},
		{"prompts/system.txt", false, "resource"},
	}
	for _, c := range cases {
		if got := isSecretFile(c.path); got != c.want {
			t.Errorf("%s: isSecretFile(%q) = %v, want %v", c.label, c.path, got, c.want)
		}
	}
}
