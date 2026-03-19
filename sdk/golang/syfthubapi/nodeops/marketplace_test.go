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
