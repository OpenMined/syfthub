package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/openmined/syfthub-desktop-gui/internal/app"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
)

// readmeWithMounts mirrors the real claude-agent frontmatter: a container.image
// plus one existing mount, alongside unrelated keys (accepts_attachments,
// runtime, sandbox) that must survive a mounts mutation untouched.
const readmeWithMounts = `---
name: Claude Agent
type: agent
version: 2.3.0
accepts_attachments: true
runtime:
    mode: container
    timeout: 300
sandbox:
    expose_resources:
        - prompts/
container:
    image: syfthub/endpoint-runner:latest
    mounts:
        - read_only: true
          source: ~/.claude/.credentials.json
          target: /home/runner/.claude/.credentials.json
---

# Claude Agent

Body content that must be preserved.
`

func writeEndpoint(t *testing.T, dir, slug, readme string) string {
	t.Helper()
	epDir := filepath.Join(dir, slug)
	if err := os.MkdirAll(epDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	readmePath := filepath.Join(epDir, "README.md")
	if err := os.WriteFile(readmePath, []byte(readme), 0o644); err != nil {
		t.Fatalf("write README: %v", err)
	}
	return readmePath
}

func TestNormalizeMountTarget(t *testing.T) {
	cases := []struct {
		in      string
		want    string
		wantErr bool
	}{
		{"work", "/home/runner/volumes/work", false},       // bare suffix lands under volumes/
		{"/work", "", true},                                // absolute but outside volumes/
		{"sub/dir", "/home/runner/volumes/sub/dir", false}, // nested bare suffix
		{"/home/runner/volumes/work", "/home/runner/volumes/work", false},
		{"/home/runner/volumes/a/../b", "/home/runner/volumes/b", false},
		{"/home/runner/work", "", true},           // under /home/runner but NOT volumes/ → invisible, rejected
		{"/home/runner/volumes/../etc", "", true}, // ../ escape out of volumes/
		{"/home/runner/../etc/passwd", "", true},  // ../ escape
		{"/etc/passwd", "", true},
		{"/home/runner/volumes", "", true}, // the volumes prefix itself
		{"/home/runner", "", true},
		{"/home/runner/", "", true},
		{"", "", true},
		{"  ", "", true},
	}
	for _, c := range cases {
		got, err := normalizeMountTarget(c.in)
		if c.wantErr {
			if err == nil {
				t.Errorf("normalizeMountTarget(%q) = %q, want error", c.in, got)
			}
			continue
		}
		if err != nil {
			t.Errorf("normalizeMountTarget(%q) unexpected error: %v", c.in, err)
			continue
		}
		if got != c.want {
			t.Errorf("normalizeMountTarget(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestCollapseHomeAndExpandMountSource(t *testing.T) {
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		t.Skip("no home dir")
	}
	in := filepath.Join(home, "Documents", "Vault")
	collapsed := collapseHome(in)
	if collapsed != "~/Documents/Vault" {
		t.Errorf("collapseHome(%q) = %q, want ~/Documents/Vault", in, collapsed)
	}
	// Round-trips through the SDK's expansion — the same code that runs at
	// mount time, so the UI stats exactly what the container will mount.
	if got, err := filemode.ExpandMountSource(collapsed); err != nil || got != in {
		t.Errorf("ExpandMountSource(%q) = %q, %v; want %q", collapsed, got, err, in)
	}
	// A non-home path is returned verbatim.
	if got := collapseHome("/tmp/x"); got != "/tmp/x" {
		t.Errorf("collapseHome(/tmp/x) = %q, want /tmp/x", got)
	}
}

func TestMountRoundTripPreservesFrontmatter(t *testing.T) {
	tmp := t.TempDir()
	const slug = "claude-agent"
	readmePath := writeEndpoint(t, tmp, slug, readmeWithMounts)
	a := &App{config: &app.Config{EndpointsPath: tmp}}

	// A real source dir so isDir resolves true.
	workSrc := filepath.Join(tmp, "worksrc")
	if err := os.MkdirAll(workSrc, 0o755); err != nil {
		t.Fatalf("mkdir worksrc: %v", err)
	}

	// Initial read: the one pre-existing mount.
	mounts, err := a.GetEndpointMounts(slug)
	if err != nil {
		t.Fatalf("GetEndpointMounts: %v", err)
	}
	if len(mounts) != 1 || mounts[0].Target != "/home/runner/.claude/.credentials.json" {
		t.Fatalf("expected 1 pre-existing mount, got %+v", mounts)
	}

	// Add a second mount via a bare suffix; it should be normalized under
	// volumes/ + stored.
	if err := a.SetEndpointMount(slug, workSrc, "work", true); err != nil {
		t.Fatalf("SetEndpointMount add: %v", err)
	}
	mounts, _ = a.GetEndpointMounts(slug)
	if len(mounts) != 2 {
		t.Fatalf("expected 2 mounts after add, got %d: %+v", len(mounts), mounts)
	}
	work := findMount(mounts, "/home/runner/volumes/work")
	if work == nil {
		t.Fatalf("work mount missing: %+v", mounts)
	}
	if !work.ReadOnly || !work.IsDir || work.Source != workSrc {
		t.Errorf("work mount = %+v, want readOnly+isDir, source=%q", *work, workSrc)
	}

	// Unrelated frontmatter and the existing image must survive the write.
	raw, _ := os.ReadFile(readmePath)
	for _, must := range []string{
		"accepts_attachments",
		"syfthub/endpoint-runner:latest",
		"expose_resources",
		"timeout",
		"Body content that must be preserved.",
	} {
		if !strings.Contains(string(raw), must) {
			t.Errorf("README lost %q after mount mutation:\n%s", must, raw)
		}
	}

	// Upsert: same target, flip read-only — count stays 2, flag changes.
	if err := a.SetEndpointMount(slug, workSrc, "/home/runner/volumes/work", false); err != nil {
		t.Fatalf("SetEndpointMount upsert: %v", err)
	}
	mounts, _ = a.GetEndpointMounts(slug)
	if len(mounts) != 2 {
		t.Fatalf("upsert changed count: %d", len(mounts))
	}
	if w := findMount(mounts, "/home/runner/volumes/work"); w == nil || w.ReadOnly {
		t.Errorf("upsert did not flip read-only: %+v", mounts)
	}

	// Delete the credentials mount, leaving only work.
	if err := a.DeleteEndpointMount(slug, "/home/runner/.claude/.credentials.json"); err != nil {
		t.Fatalf("DeleteEndpointMount: %v", err)
	}
	mounts, _ = a.GetEndpointMounts(slug)
	if len(mounts) != 1 || mounts[0].Target != "/home/runner/volumes/work" {
		t.Fatalf("expected only work mount after delete, got %+v", mounts)
	}

	// Batch add: one write for several paths, targets derived from basenames.
	docsSrc := filepath.Join(tmp, "docs")
	if err := os.MkdirAll(docsSrc, 0o755); err != nil {
		t.Fatalf("mkdir docs: %v", err)
	}
	if err := a.AddEndpointMounts(slug, []string{docsSrc, workSrc}); err != nil {
		t.Fatalf("AddEndpointMounts: %v", err)
	}
	mounts, _ = a.GetEndpointMounts(slug)
	if len(mounts) != 3 {
		t.Fatalf("expected 3 mounts after batch add, got %+v", mounts)
	}
	docs := findMount(mounts, "/home/runner/volumes/docs")
	if docs == nil || !docs.ReadOnly {
		t.Errorf("batch add missing read-only volumes/docs mount: %+v", mounts)
	}
	if findMount(mounts, "/home/runner/volumes/worksrc") == nil {
		t.Errorf("batch add missing volumes/worksrc mount: %+v", mounts)
	}

	// All-unusable batch input is an error, not a silent no-op.
	if err := a.AddEndpointMounts(slug, []string{"", "   "}); err == nil {
		t.Error("expected error for batch add with no usable sources")
	}
}

func TestSetEndpointMountRejectsBadTarget(t *testing.T) {
	tmp := t.TempDir()
	const slug = "claude-agent"
	writeEndpoint(t, tmp, slug, readmeWithMounts)
	a := &App{config: &app.Config{EndpointsPath: tmp}}

	if err := a.SetEndpointMount(slug, "/tmp/x", "/etc/passwd", true); err == nil {
		t.Error("expected error for target outside the sandbox")
	}
	// Under /home/runner/ but outside volumes/ — invisible inside the sandbox,
	// so it must be rejected rather than silently dropped.
	if err := a.SetEndpointMount(slug, "/tmp/x", "/home/runner/work", true); err == nil {
		t.Error("expected error for target outside /home/runner/volumes/")
	}
	if err := a.SetEndpointMount(slug, "", "work", true); err == nil {
		t.Error("expected error for empty source")
	}
}

func findMount(mounts []MountEntry, target string) *MountEntry {
	for i := range mounts {
		if mounts[i].Target == target {
			return &mounts[i]
		}
	}
	return nil
}

// readmeWithSandbox carries an unmanaged key (workspace.quota_mb) plus sibling
// frontmatter (accepts_attachments, container.image) that a sandbox write must
// preserve.
const readmeWithSandbox = `---
name: Claude Agent
type: agent
accepts_attachments: true
container:
    image: syfthub/endpoint-runner:latest
sandbox:
    allow_subprocess: false
    workspace:
        quota_mb: 100
---

# Body
`

func TestSandboxRoundTripPreservesUnmanagedKeys(t *testing.T) {
	tmp := t.TempDir()
	const slug = "claude-agent"
	readmePath := writeEndpoint(t, tmp, slug, readmeWithSandbox)
	a := &App{config: &app.Config{EndpointsPath: tmp}}

	if _, err := a.GetEndpointSandbox(slug); err != nil {
		t.Fatalf("GetEndpointSandbox: %v", err)
	}

	in := SandboxSettings{
		ExposeEnv:       []string{"  API_KEY  ", "API_KEY", ""}, // dup+blank+ws
		ExposeResources: []string{"prompts/"},
		WorkspaceScope:  "per_session",
		MemoryMB:        2048,
	}
	if err := a.SetEndpointSandbox(slug, in); err != nil {
		t.Fatalf("SetEndpointSandbox: %v", err)
	}

	got, _ := a.GetEndpointSandbox(slug)
	if len(got.ExposeEnv) != 1 || got.ExposeEnv[0] != "API_KEY" {
		t.Errorf("expose_env not trimmed/deduped: %+v", got.ExposeEnv)
	}
	if got.WorkspaceScope != "per_session" {
		t.Errorf("workspace scope = %q, want per_session", got.WorkspaceScope)
	}
	if got.MemoryMB != 2048 {
		t.Errorf("memory_mb = %d, want 2048", got.MemoryMB)
	}

	raw, _ := os.ReadFile(readmePath)
	for _, must := range []string{"quota_mb", "accepts_attachments", "endpoint-runner:latest", "# Body"} {
		if !strings.Contains(string(raw), must) {
			t.Errorf("sandbox write dropped %q:\n%s", must, raw)
		}
	}
	// The obsolete allow_subprocess key (present in the fixture) must be
	// stripped on write — subprocesses are always permitted now.
	if strings.Contains(string(raw), "allow_subprocess") {
		t.Errorf("obsolete allow_subprocess key not stripped:\n%s", raw)
	}
}

func TestSandboxValidation(t *testing.T) {
	tmp := t.TempDir()
	const slug = "claude-agent"
	writeEndpoint(t, tmp, slug, readmeWithSandbox)
	a := &App{config: &app.Config{EndpointsPath: tmp}}

	if err := a.SetEndpointSandbox(slug, SandboxSettings{WorkspaceScope: "weird"}); err == nil {
		t.Error("expected error for invalid workspace scope")
	}

	// Clearing back to defaults should drop the managed keys while leaving the
	// file valid.
	if err := a.SetEndpointSandbox(slug, SandboxSettings{ExposeEnv: []string{"FOO"}}); err != nil {
		t.Fatalf("set sandbox: %v", err)
	}
	if err := a.SetEndpointSandbox(slug, SandboxSettings{}); err != nil {
		t.Fatalf("reset sandbox: %v", err)
	}
	got, _ := a.GetEndpointSandbox(slug)
	if len(got.ExposeEnv) != 0 {
		t.Errorf("reset did not clear managed keys: %+v", got)
	}
}
