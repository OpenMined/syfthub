package nodeops

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestParseReadmeFrontmatter(t *testing.T) {
	dir := t.TempDir()
	readmePath := filepath.Join(dir, "README.md")

	content := `---
slug: my-model
name: My Model
description: A test model
type: model
version: "1.0.0"
enabled: true
---

# My Model

Some body content.
`
	if err := os.WriteFile(readmePath, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	fm, body, err := ParseReadmeFrontmatter(readmePath)
	if err != nil {
		t.Fatal(err)
	}

	if fm.Slug != "my-model" {
		t.Errorf("Slug = %q, want %q", fm.Slug, "my-model")
	}
	if fm.Name != "My Model" {
		t.Errorf("Name = %q, want %q", fm.Name, "My Model")
	}
	if fm.Type != "model" {
		t.Errorf("Type = %q, want %q", fm.Type, "model")
	}
	if fm.Enabled == nil || !*fm.Enabled {
		t.Error("Enabled should be true")
	}
	if !strings.Contains(body, "Some body content") {
		t.Errorf("body = %q, should contain 'Some body content'", body)
	}
}

func TestParseReadmeFrontmatter_NoFrontmatter(t *testing.T) {
	dir := t.TempDir()
	readmePath := filepath.Join(dir, "README.md")

	if err := os.WriteFile(readmePath, []byte("# Just markdown"), 0644); err != nil {
		t.Fatal(err)
	}

	_, _, err := ParseReadmeFrontmatter(readmePath)
	if err == nil {
		t.Error("expected error for file without frontmatter")
	}
}

func TestUpdateReadmeFrontmatter(t *testing.T) {
	dir := t.TempDir()
	readmePath := filepath.Join(dir, "README.md")

	content := `---
slug: my-model
name: My Model
type: model
version: "1.0.0"
---

# My Model
`
	if err := os.WriteFile(readmePath, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	updates := map[string]interface{}{
		"name":    "Updated Model",
		"version": "2.0.0",
	}
	if err := UpdateReadmeFrontmatter(readmePath, updates); err != nil {
		t.Fatal(err)
	}

	fm, _, err := ParseReadmeFrontmatter(readmePath)
	if err != nil {
		t.Fatal(err)
	}

	if fm.Name != "Updated Model" {
		t.Errorf("Name = %q, want %q", fm.Name, "Updated Model")
	}
	if fm.Version != "2.0.0" {
		t.Errorf("Version = %q, want %q", fm.Version, "2.0.0")
	}
	// Slug should be preserved
	if fm.Slug != "my-model" {
		t.Errorf("Slug = %q, want %q", fm.Slug, "my-model")
	}
}

func TestWriteReadmeWithFrontmatter(t *testing.T) {
	dir := t.TempDir()
	readmePath := filepath.Join(dir, "README.md")

	enabled := true
	fm := &ReadmeFrontmatter{
		Slug:    "test-ep",
		Name:    "Test EP",
		Type:    "model",
		Version: "1.0.0",
		Enabled: &enabled,
	}

	if err := WriteReadmeWithFrontmatter(readmePath, fm, "# Hello\n\nWorld."); err != nil {
		t.Fatal(err)
	}

	parsed, body, err := ParseReadmeFrontmatter(readmePath)
	if err != nil {
		t.Fatal(err)
	}
	if parsed.Slug != "test-ep" {
		t.Errorf("Slug = %q, want %q", parsed.Slug, "test-ep")
	}
	if !strings.Contains(body, "Hello") {
		t.Errorf("body = %q, should contain 'Hello'", body)
	}
}
