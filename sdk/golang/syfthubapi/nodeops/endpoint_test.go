package nodeops

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCreateEndpoint(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	slug, err := mgr.CreateEndpoint(CreateEndpointRequest{
		Name: "My Test Model",
		Type: "model",
	})
	if err != nil {
		t.Fatal(err)
	}

	if slug != "my-test-model" {
		t.Errorf("slug = %q, want %q", slug, "my-test-model")
	}

	// Verify files were created
	for _, file := range []string{"runner.py", "pyproject.toml", "README.md"} {
		path := filepath.Join(dir, slug, file)
		if _, err := os.Stat(path); os.IsNotExist(err) {
			t.Errorf("expected %s to exist", file)
		}
	}

	// Verify frontmatter
	fm, _, err := ParseReadmeFrontmatter(filepath.Join(dir, slug, "README.md"))
	if err != nil {
		t.Fatal(err)
	}
	if fm.Name != "My Test Model" {
		t.Errorf("frontmatter Name = %q, want %q", fm.Name, "My Test Model")
	}
	if fm.Type != "model" {
		t.Errorf("frontmatter Type = %q, want %q", fm.Type, "model")
	}
}

func TestCreateEndpoint_AlreadyExists(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	_, err := mgr.CreateEndpoint(CreateEndpointRequest{Name: "test", Type: "model"})
	if err != nil {
		t.Fatal(err)
	}

	_, err = mgr.CreateEndpoint(CreateEndpointRequest{Name: "test", Type: "model"})
	if err == nil {
		t.Error("expected error for duplicate endpoint")
	}
}

func TestCreateEndpoint_InvalidType(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	_, err := mgr.CreateEndpoint(CreateEndpointRequest{Name: "test", Type: "invalid"})
	if err == nil {
		t.Error("expected error for invalid type")
	}
}

func TestDeleteEndpoint(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	slug, _ := mgr.CreateEndpoint(CreateEndpointRequest{Name: "deleteme", Type: "model"})

	if err := mgr.DeleteEndpoint(slug); err != nil {
		t.Fatal(err)
	}

	if _, err := os.Stat(filepath.Join(dir, slug)); !os.IsNotExist(err) {
		t.Error("endpoint directory should be deleted")
	}
}

func TestDeleteEndpoint_NotFound(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	if err := mgr.DeleteEndpoint("nonexistent"); err == nil {
		t.Error("expected error for nonexistent endpoint")
	}
}

func TestDeleteEndpoint_PathTraversal(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	if err := mgr.DeleteEndpoint("../etc"); err == nil {
		t.Error("expected error for path traversal attempt")
	}
}

func TestListEndpoints(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	mgr.CreateEndpoint(CreateEndpointRequest{Name: "Model A", Type: "model"})
	mgr.CreateEndpoint(CreateEndpointRequest{Name: "Data B", Type: "data_source"})

	endpoints, err := mgr.ListEndpoints()
	if err != nil {
		t.Fatal(err)
	}

	if len(endpoints) != 2 {
		t.Errorf("expected 2 endpoints, got %d", len(endpoints))
	}
}

func TestListEndpoints_Empty(t *testing.T) {
	dir := t.TempDir()
	mgr := NewManager(dir)

	endpoints, err := mgr.ListEndpoints()
	if err != nil {
		t.Fatal(err)
	}

	if len(endpoints) != 0 {
		t.Errorf("expected 0 endpoints, got %d", len(endpoints))
	}
}
