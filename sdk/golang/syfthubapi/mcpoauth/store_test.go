package mcpoauth

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"golang.org/x/oauth2"
)

func TestFileStoreRoundTripAndPerms(t *testing.T) {
	dir := t.TempDir()
	store := NewFileStore(dir)

	if rec, err := store.Load("figma"); err != nil || rec != nil {
		t.Fatalf("missing load = %v, %v; want nil,nil", rec, err)
	}

	rec := &Record{
		AuthServer: "https://as", ClientID: "c", Resource: "https://r/mcp",
		Token: &oauth2.Token{AccessToken: "a", RefreshToken: "r", Expiry: time.Now().Add(time.Hour)},
	}
	if err := store.Save("figma", rec); err != nil {
		t.Fatalf("save: %v", err)
	}
	info, err := os.Stat(filepath.Join(dir, "figma.json"))
	if err != nil {
		t.Fatal(err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("token file perm = %o, want 600", perm)
	}
	got, _ := store.Load("figma")
	if got.ClientID != "c" || got.Token.AccessToken != "a" {
		t.Errorf("round-trip lost data: %+v", got)
	}

	if err := store.Delete("figma"); err != nil {
		t.Fatalf("delete: %v", err)
	}
	if got, _ := store.Load("figma"); got != nil {
		t.Errorf("after delete = %+v, want nil", got)
	}
	// Unsafe names are rejected, not written outside the dir.
	if _, ok := store.path("../escape"); ok {
		t.Error("unsafe server name accepted")
	}
}

func TestServerStatus(t *testing.T) {
	store := NewFileStore(t.TempDir())
	if st, _ := ServerStatus(store, "x"); st != StatusNotConnected {
		t.Errorf("no record status = %q, want not_connected", st)
	}
	// Live token → connected.
	_ = store.Save("x", &Record{Token: &oauth2.Token{AccessToken: "a", RefreshToken: "r", Expiry: time.Now().Add(time.Hour)}})
	if st, _ := ServerStatus(store, "x"); st != StatusConnected {
		t.Errorf("live status = %q, want connected", st)
	}
	// Expired access, no refresh → expired (needs reconnect).
	_ = store.Save("x", &Record{Token: &oauth2.Token{AccessToken: "a", Expiry: time.Now().Add(-time.Hour)}})
	if st, _ := ServerStatus(store, "x"); st != StatusExpired {
		t.Errorf("expired status = %q, want expired", st)
	}
}

func TestHandlerNotConnected(t *testing.T) {
	store := NewFileStore(t.TempDir())
	if _, err := Handler(context.Background(), store, "x", nil); err != ErrNotConnected {
		t.Errorf("Handler with no record err = %v, want ErrNotConnected", err)
	}
}

func TestDiscoverNoAuthRequired(t *testing.T) {
	// A server that answers 200 (no 401) needs no OAuth.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{"jsonrpc": "2.0", "id": 1, "result": map[string]any{}})
	}))
	defer srv.Close()
	if _, err := Discover(context.Background(), srv.URL, nil); err != ErrAuthNotRequired {
		t.Errorf("Discover err = %v, want ErrAuthNotRequired", err)
	}
}

func TestResourceMetadataURLFallback(t *testing.T) {
	// No resource_metadata param → fall back to the well-known path at origin.
	got := resourceMetadataURL([]string{`Bearer realm="x"`}, "https://mcp.figma.com/mcp")
	if want := "https://mcp.figma.com/.well-known/oauth-protected-resource"; got != want {
		t.Errorf("fallback = %q, want %q", got, want)
	}
	// With the param → use it verbatim.
	got = resourceMetadataURL([]string{`Bearer resource_metadata="https://x/.well-known/oauth-protected-resource/mcp"`}, "https://x/mcp")
	if want := "https://x/.well-known/oauth-protected-resource/mcp"; got != want {
		t.Errorf("param = %q, want %q", got, want)
	}
}
