package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestEgressSocketPath(t *testing.T) {
	p := &egressProvisioner{socketDir: "/Users/short/.syfthub-desktop/egress/sockets"}

	// A short slug uses the plain "<slug>.sock" name.
	if got := p.socketPath("basic-agent"); got != filepath.Join(p.socketDir, "basic-agent.sock") {
		t.Errorf("short slug path = %q, want plain name", got)
	}

	// A pathologically long slug folds to a short hash so the AF_UNIX sun_path
	// limit can't be exceeded, and the result is deterministic.
	long := strings.Repeat("x", 120)
	got := p.socketPath(long)
	if len(got) > maxUnixSocketPath {
		t.Errorf("long slug path = %q (%d bytes), want <= %d", got, len(got), maxUnixSocketPath)
	}
	if got != p.socketPath(long) {
		t.Errorf("socketPath not deterministic for the same slug")
	}
	if !strings.HasSuffix(got, ".sock") || strings.Contains(filepath.Base(got), "x") {
		t.Errorf("long slug path = %q, want a short hashed .sock name", got)
	}
}

func TestEgressKeyStore(t *testing.T) {
	s := &egressKeyStore{dir: filepath.Join(t.TempDir(), "keys")}

	if v, err := s.Get("basic-agent"); err != nil || v != "" {
		t.Fatalf("Get missing = %q, %v; want empty", v, err)
	}
	if err := s.Set("basic-agent", "  sk-real-123  "); err != nil {
		t.Fatalf("Set: %v", err)
	}
	if v, _ := s.Get("basic-agent"); v != "sk-real-123" {
		t.Errorf("Get = %q, want trimmed sk-real-123", v)
	}
	if err := s.Clear("basic-agent"); err != nil {
		t.Fatalf("Clear: %v", err)
	}
	if v, _ := s.Get("basic-agent"); v != "" {
		t.Errorf("after Clear Get = %q, want empty", v)
	}
	// Clear of a missing key is a no-op, not an error.
	if err := s.Clear("nope"); err != nil {
		t.Errorf("Clear missing: %v", err)
	}
}
