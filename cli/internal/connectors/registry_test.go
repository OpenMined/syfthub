package connectors

import (
	"testing"
)

func TestNewRegistry_LoadsTemplates(t *testing.T) {
	r := NewRegistry()
	metas := r.List()

	if len(metas) == 0 {
		t.Fatal("expected at least one connector template to be loaded")
	}

	// Verify all expected connectors are loaded
	expected := []string{
		"anthropic",
		"custom-api",
		"github",
		"google-drive",
		"google-sheets",
		"notion",
		"openai",
		"postgres",
		"slack",
		"telegram",
	}

	loaded := make(map[string]bool)
	for _, m := range metas {
		loaded[m.ID] = true
	}

	for _, id := range expected {
		if !loaded[id] {
			t.Errorf("expected connector '%s' to be loaded", id)
		}
	}
}

func TestRegistry_Get_Found(t *testing.T) {
	r := NewRegistry()

	tmpl, err := r.Get("telegram")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if tmpl.Meta.Name != "Telegram" {
		t.Errorf("expected name 'Telegram', got '%s'", tmpl.Meta.Name)
	}
	if tmpl.Meta.Category != "communication" {
		t.Errorf("expected category 'communication', got '%s'", tmpl.Meta.Category)
	}
	if len(tmpl.Steps) == 0 {
		t.Error("expected at least one step")
	}
}

func TestRegistry_Get_NotFound(t *testing.T) {
	r := NewRegistry()

	_, err := r.Get("nonexistent")
	if err == nil {
		t.Fatal("expected error for nonexistent connector")
	}
}

func TestRegistry_List_Sorted(t *testing.T) {
	r := NewRegistry()
	metas := r.List()

	for i := 1; i < len(metas); i++ {
		if metas[i].ID < metas[i-1].ID {
			t.Errorf("list not sorted: '%s' comes after '%s'", metas[i].ID, metas[i-1].ID)
		}
	}
}

func TestRegistry_Scaffold_SingleConnector(t *testing.T) {
	r := NewRegistry()

	spec, err := r.Scaffold([]string{"openai"}, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if spec.Version != "1" {
		t.Errorf("expected version '1', got '%s'", spec.Version)
	}

	if len(spec.Steps) == 0 {
		t.Error("expected at least one step")
	}

	// OpenAI has no lifecycle (no OAuth)
	if spec.Lifecycle != nil {
		t.Error("expected no lifecycle for openai connector")
	}
}

func TestRegistry_Scaffold_WithLifecycle(t *testing.T) {
	r := NewRegistry()

	spec, err := r.Scaffold([]string{"google-drive"}, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if spec.Lifecycle == nil {
		t.Fatal("expected lifecycle config for google-drive")
	}
	if spec.Lifecycle.Refresh == nil {
		t.Fatal("expected refresh config")
	}
	if spec.Lifecycle.Refresh.Strategy != "refresh_token" {
		t.Errorf("expected strategy 'refresh_token', got '%s'", spec.Lifecycle.Refresh.Strategy)
	}
}

func TestRegistry_Scaffold_MultipleConnectors(t *testing.T) {
	r := NewRegistry()

	spec, err := r.Scaffold([]string{"openai", "anthropic"}, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Both have an "api_key" step and "model" step — should be prefixed to avoid conflict
	stepIDs := make(map[string]bool)
	for _, step := range spec.Steps {
		if stepIDs[step.ID] {
			t.Errorf("duplicate step ID: '%s'", step.ID)
		}
		stepIDs[step.ID] = true
	}

	// Should have steps from both connectors
	if len(spec.Steps) < 4 {
		t.Errorf("expected at least 4 steps (2 from each), got %d", len(spec.Steps))
	}
}

func TestRegistry_Scaffold_NoConnectors(t *testing.T) {
	r := NewRegistry()

	_, err := r.Scaffold([]string{}, nil)
	if err == nil {
		t.Fatal("expected error for empty connector list")
	}
}

func TestRegistry_Scaffold_InvalidConnector(t *testing.T) {
	r := NewRegistry()

	_, err := r.Scaffold([]string{"nonexistent"}, nil)
	if err == nil {
		t.Fatal("expected error for nonexistent connector")
	}
}

func TestRegistry_ConnectorHasSteps(t *testing.T) {
	r := NewRegistry()

	// Verify every connector has at least one step
	for _, meta := range r.List() {
		tmpl, err := r.Get(meta.ID)
		if err != nil {
			t.Errorf("failed to get connector '%s': %v", meta.ID, err)
			continue
		}
		if len(tmpl.Steps) == 0 {
			t.Errorf("connector '%s' has no steps", meta.ID)
		}
		if tmpl.Meta.Name == "" {
			t.Errorf("connector '%s' has empty name", meta.ID)
		}
		if tmpl.Meta.Description == "" {
			t.Errorf("connector '%s' has empty description", meta.ID)
		}
	}
}
