package mcpbridge

import (
	"strings"
	"testing"
)

func TestChildEnvLayersRegistryOverHost(t *testing.T) {
	t.Setenv("PATH", "/usr/bin")
	t.Setenv("DESKTOP_SECRET", "should-not-leak")

	env := childEnv(map[string]string{"GITHUB_TOKEN": "ghp_xxx"})
	joined := strings.Join(env, "\n")

	if !strings.Contains(joined, "PATH=/usr/bin") {
		t.Errorf("PATH not passed through: %v", env)
	}
	if !strings.Contains(joined, "GITHUB_TOKEN=ghp_xxx") {
		t.Errorf("registry env not applied: %v", env)
	}
	if strings.Contains(joined, "DESKTOP_SECRET") {
		t.Errorf("unrelated host secret leaked into child env: %v", env)
	}
}

func TestNewStdioRejectsEmptyCommand(t *testing.T) {
	if _, err := NewStdio("x", Config{Command: nil}, nil); err == nil {
		t.Error("expected error for empty command")
	}
	if _, err := NewStdio("x", Config{Command: []string{"true"}}, nil); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}
