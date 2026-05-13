package nodeops

import (
	"archive/zip"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestFetchPackages(t *testing.T) {
	manifest := MarketplaceManifest{
		Packages: []MarketplacePackage{
			{Slug: "pkg-1", Name: "Package 1", Type: "model", Version: "1.0"},
			{Slug: "pkg-2", Name: "Package 2", Type: "data_source", Version: "2.0"},
		},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(manifest)
	}))
	defer server.Close()

	client := NewMarketplaceClient(server.URL)
	pkgs, err := client.FetchPackages()
	if err != nil {
		t.Fatal(err)
	}

	if len(pkgs) != 2 {
		t.Fatalf("expected 2 packages, got %d", len(pkgs))
	}
	if pkgs[0].Slug != "pkg-1" {
		t.Errorf("first package slug = %q, want %q", pkgs[0].Slug, "pkg-1")
	}
}

func TestFetchPackages_ServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	client := NewMarketplaceClient(server.URL)
	_, err := client.FetchPackages()
	if err == nil {
		t.Error("expected error for 500 response")
	}
}

func TestInstallPackage(t *testing.T) {
	dir := t.TempDir()

	// Create a test zip file
	zipPath := filepath.Join(dir, "test.zip")
	createTestZip(t, zipPath, map[string]string{
		"runner.py":      "# test runner",
		"pyproject.toml": "[project]\nname = \"test\"\n",
	})

	zipData, _ := os.ReadFile(zipPath)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(zipData)
	}))
	defer server.Close()

	endpointsDir := filepath.Join(dir, "endpoints")
	os.MkdirAll(endpointsDir, 0755)

	client := NewMarketplaceClient("http://unused")
	err := client.InstallPackage(endpointsDir, "test-pkg", server.URL)
	if err != nil {
		t.Fatal(err)
	}

	// Verify files were extracted
	if _, err := os.Stat(filepath.Join(endpointsDir, "test-pkg", "runner.py")); os.IsNotExist(err) {
		t.Error("expected runner.py to be extracted")
	}
}

func TestFetchPackages_EmptyManifest(t *testing.T) {
	manifest := MarketplaceManifest{
		Packages: []MarketplacePackage{},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(manifest)
	}))
	defer server.Close()

	client := NewMarketplaceClient(server.URL)
	pkgs, err := client.FetchPackages()
	if err != nil {
		t.Fatal(err)
	}

	if len(pkgs) != 0 {
		t.Fatalf("expected 0 packages, got %d", len(pkgs))
	}
}

func TestFetchPackages_EmptyURL(t *testing.T) {
	client := NewMarketplaceClient("")
	_, err := client.FetchPackages()
	if err == nil {
		t.Error("expected error for empty marketplace URL")
	}
}

func TestFetchPackages_InvalidJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not valid json"))
	}))
	defer server.Close()

	client := NewMarketplaceClient(server.URL)
	_, err := client.FetchPackages()
	if err == nil {
		t.Error("expected error for invalid JSON response")
	}
}

func TestFetchPackages_AllFields(t *testing.T) {
	manifest := MarketplaceManifest{
		Packages: []MarketplacePackage{
			{
				Slug:        "agent-pkg",
				Name:        "Agent Package",
				Description: "An agent endpoint",
				Type:        "agent",
				Author:      "testuser",
				Version:     "1.2.3",
				DownloadURL: "https://example.com/agent.zip",
				Tags:        []string{"agent", "ai", "chat"},
			},
		},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(manifest)
	}))
	defer server.Close()

	client := NewMarketplaceClient(server.URL)
	pkgs, err := client.FetchPackages()
	if err != nil {
		t.Fatal(err)
	}

	if len(pkgs) != 1 {
		t.Fatalf("expected 1 package, got %d", len(pkgs))
	}

	pkg := pkgs[0]
	if pkg.Slug != "agent-pkg" {
		t.Errorf("Slug = %q, want %q", pkg.Slug, "agent-pkg")
	}
	if pkg.Name != "Agent Package" {
		t.Errorf("Name = %q, want %q", pkg.Name, "Agent Package")
	}
	if pkg.Description != "An agent endpoint" {
		t.Errorf("Description = %q", pkg.Description)
	}
	if pkg.Type != "agent" {
		t.Errorf("Type = %q, want %q", pkg.Type, "agent")
	}
	if pkg.Author != "testuser" {
		t.Errorf("Author = %q, want %q", pkg.Author, "testuser")
	}
	if pkg.Version != "1.2.3" {
		t.Errorf("Version = %q, want %q", pkg.Version, "1.2.3")
	}
	if pkg.DownloadURL != "https://example.com/agent.zip" {
		t.Errorf("DownloadURL = %q", pkg.DownloadURL)
	}
	if len(pkg.Tags) != 3 {
		t.Fatalf("expected 3 tags, got %d", len(pkg.Tags))
	}
	if pkg.Tags[0] != "agent" || pkg.Tags[1] != "ai" || pkg.Tags[2] != "chat" {
		t.Errorf("Tags = %v", pkg.Tags)
	}
}

func TestFetchPackages_MultipleTypes(t *testing.T) {
	manifest := MarketplaceManifest{
		Packages: []MarketplacePackage{
			{Slug: "model-1", Name: "Model 1", Type: "model", Version: "1.0"},
			{Slug: "ds-1", Name: "Data Source 1", Type: "data_source", Version: "1.0"},
			{Slug: "agent-1", Name: "Agent 1", Type: "agent", Version: "1.0", Tags: []string{"agent"}},
			{Slug: "model-2", Name: "Model 2", Type: "model", Version: "2.0"},
		},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(manifest)
	}))
	defer server.Close()

	client := NewMarketplaceClient(server.URL)
	pkgs, err := client.FetchPackages()
	if err != nil {
		t.Fatal(err)
	}

	if len(pkgs) != 4 {
		t.Fatalf("expected 4 packages, got %d", len(pkgs))
	}

	// Verify filtering by type can be done client-side
	models := filterByType(pkgs, "model")
	if len(models) != 2 {
		t.Errorf("expected 2 models, got %d", len(models))
	}

	agents := filterByType(pkgs, "agent")
	if len(agents) != 1 {
		t.Errorf("expected 1 agent, got %d", len(agents))
	}

	dataSources := filterByType(pkgs, "data_source")
	if len(dataSources) != 1 {
		t.Errorf("expected 1 data_source, got %d", len(dataSources))
	}
}

func TestFetchPackages_TagFiltering(t *testing.T) {
	manifest := MarketplaceManifest{
		Packages: []MarketplacePackage{
			{Slug: "p1", Name: "P1", Type: "model", Tags: []string{"ai", "nlp"}},
			{Slug: "p2", Name: "P2", Type: "agent", Tags: []string{"agent", "chat"}},
			{Slug: "p3", Name: "P3", Type: "model", Tags: []string{"agent", "vision"}},
			{Slug: "p4", Name: "P4", Type: "data_source", Tags: nil},
		},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(manifest)
	}))
	defer server.Close()

	client := NewMarketplaceClient(server.URL)
	pkgs, err := client.FetchPackages()
	if err != nil {
		t.Fatal(err)
	}

	// Filter by "agent" tag
	agentTagged := filterByTag(pkgs, "agent")
	if len(agentTagged) != 2 {
		t.Errorf("expected 2 packages with 'agent' tag, got %d", len(agentTagged))
	}

	// Filter by "nlp" tag
	nlpTagged := filterByTag(pkgs, "nlp")
	if len(nlpTagged) != 1 {
		t.Errorf("expected 1 package with 'nlp' tag, got %d", len(nlpTagged))
	}

	// Filter by non-existent tag
	noneTagged := filterByTag(pkgs, "nonexistent")
	if len(noneTagged) != 0 {
		t.Errorf("expected 0 packages with 'nonexistent' tag, got %d", len(noneTagged))
	}
}

func TestMarketplaceManifest_JSONRoundTrip(t *testing.T) {
	manifest := MarketplaceManifest{
		Packages: []MarketplacePackage{
			{
				Slug:        "test-pkg",
				Name:        "Test Package",
				Description: "A test package",
				Type:        "model",
				Author:      "author",
				Version:     "1.0.0",
				DownloadURL: "https://example.com/test.zip",
				Tags:        []string{"test", "model"},
			},
		},
	}

	data, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}

	var decoded MarketplaceManifest
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatal(err)
	}

	if len(decoded.Packages) != 1 {
		t.Fatalf("expected 1 package after round-trip, got %d", len(decoded.Packages))
	}
	if decoded.Packages[0].Slug != "test-pkg" {
		t.Errorf("Slug after round-trip = %q", decoded.Packages[0].Slug)
	}
	if decoded.Packages[0].DownloadURL != "https://example.com/test.zip" {
		t.Errorf("DownloadURL after round-trip = %q", decoded.Packages[0].DownloadURL)
	}
}

func TestNewMarketplaceClient(t *testing.T) {
	client := NewMarketplaceClient("https://example.com/manifest.json")
	if client.ManifestURL != "https://example.com/manifest.json" {
		t.Errorf("ManifestURL = %q", client.ManifestURL)
	}
	if client.HTTPClient == nil {
		t.Error("HTTPClient should not be nil")
	}
}

func TestInstallPackage_InvalidSlug(t *testing.T) {
	client := NewMarketplaceClient("http://unused")

	tests := []struct {
		name string
		slug string
	}{
		{"empty slug", ""},
		{"path traversal", ".."},
		{"slash", "some/path"},
		{"backslash", "some\\path"},
		{"double dot in name", "pkg..name"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := client.InstallPackage("/tmp/endpoints", tt.slug, "http://example.com/pkg.zip")
			if err == nil {
				t.Errorf("expected error for slug %q", tt.slug)
			}
		})
	}
}

// filterByType is a test helper that filters packages by type.
func filterByType(pkgs []MarketplacePackage, typ string) []MarketplacePackage {
	var result []MarketplacePackage
	for _, pkg := range pkgs {
		if pkg.Type == typ {
			result = append(result, pkg)
		}
	}
	return result
}

// filterByTag is a test helper that filters packages by tag.
func filterByTag(pkgs []MarketplacePackage, tag string) []MarketplacePackage {
	var result []MarketplacePackage
	for _, pkg := range pkgs {
		for _, t := range pkg.Tags {
			if t == tag {
				result = append(result, pkg)
				break
			}
		}
	}
	return result
}

func TestInstallPackage_AlreadyInstalled(t *testing.T) {
	dir := t.TempDir()
	endpointsDir := filepath.Join(dir, "endpoints")
	os.MkdirAll(filepath.Join(endpointsDir, "existing"), 0755)

	client := NewMarketplaceClient("http://unused")
	err := client.InstallPackage(endpointsDir, "existing", "http://example.com/test.zip")
	if err == nil {
		t.Error("expected error for already installed package")
	}
}

func createTestZip(t *testing.T, path string, files map[string]string) {
	t.Helper()

	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()

	w := zip.NewWriter(f)
	for name, content := range files {
		fw, err := w.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := fw.Write([]byte(content)); err != nil {
			t.Fatal(err)
		}
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
}
