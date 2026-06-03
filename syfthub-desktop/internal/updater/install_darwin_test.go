//go:build darwin

package updater

import (
	"os"
	"path/filepath"
	"testing"
)

func TestAppBundleRoot(t *testing.T) {
	cases := []struct {
		name string
		exe  string
		want string
	}{
		{
			name: "standard bundle layout",
			exe:  "/Applications/SyftHub Desktop.app/Contents/MacOS/syfthub-desktop",
			want: "/Applications/SyftHub Desktop.app",
		},
		{
			name: "bundle in a nested path",
			exe:  "/Users/me/Downloads/x/SyftHub Desktop.app/Contents/MacOS/syfthub-desktop",
			want: "/Users/me/Downloads/x/SyftHub Desktop.app",
		},
		{
			name: "bare binary, no bundle",
			exe:  "/usr/local/bin/syfthub-desktop",
			want: "",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := appBundleRoot(tc.exe); got != tc.want {
				t.Errorf("appBundleRoot(%q) = %q, want %q", tc.exe, got, tc.want)
			}
		})
	}
}

func TestFindAppBundle(t *testing.T) {
	dir := t.TempDir()
	// A __MACOSX sibling and a stray file must be ignored; the single
	// *.app directory is the match.
	if err := os.MkdirAll(filepath.Join(dir, "__MACOSX"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "readme.txt"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	appPath := filepath.Join(dir, "SyftHub Desktop.app")
	if err := os.MkdirAll(appPath, 0o755); err != nil {
		t.Fatal(err)
	}

	got, err := findAppBundle(dir)
	if err != nil {
		t.Fatalf("findAppBundle: unexpected error %v", err)
	}
	if got != appPath {
		t.Errorf("findAppBundle = %q, want %q", got, appPath)
	}
}

func TestFindAppBundleMissing(t *testing.T) {
	dir := t.TempDir()
	if _, err := findAppBundle(dir); err == nil {
		t.Error("findAppBundle on a dir with no .app should return an error")
	}
}
