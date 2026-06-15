package egressbroker

import (
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"
)

type fixedSource struct {
	cred Credential
	err  error
}

func (f fixedSource) Resolve(_ *http.Request) (Credential, error) { return f.cred, f.err }

// unixClient returns an http.Client that dials the given AF_UNIX socket for any
// request URL (the host in the URL is ignored).
func unixClient(sock string) *http.Client {
	return &http.Client{
		Timeout: 5 * time.Second,
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				return (&net.Dialer{}).DialContext(ctx, "unix", sock)
			},
		},
	}
}

func TestBrokerSwapsAuthAndForwardsPath(t *testing.T) {
	var gotAuth, gotPath, gotQuery, gotXApiKey string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		gotXApiKey = r.Header.Get("X-Api-Key")
		gotPath = r.URL.Path
		gotQuery = r.URL.RawQuery
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(200)
		w.Write([]byte("data: ok\n\n"))
	}))
	defer upstream.Close()

	sock := filepath.Join(t.TempDir(), "e.sock")
	b := New(nil)
	defer b.Stop()
	if err := b.Add(EndpointEgress{
		Slug:       "basic",
		SocketPath: sock,
		Source: fixedSource{cred: Credential{
			Upstream: upstream.URL, Headers: map[string]string{"Authorization": "Bearer REAL"},
		}},
	}); err != nil {
		t.Fatalf("Add: %v", err)
	}

	req, _ := http.NewRequest("POST", "http://broker/v1/messages?beta=1", nil)
	req.Header.Set("Authorization", "Bearer SENTINEL")
	req.Header.Set("X-Api-Key", "sentinel-key")
	req.Header.Set("anthropic-version", "2023-06-01")
	resp, err := unixClient(sock).Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	resp.Body.Close()

	if gotAuth != "Bearer REAL" {
		t.Errorf("upstream Authorization = %q, want Bearer REAL", gotAuth)
	}
	if gotXApiKey != "" {
		t.Errorf("upstream X-Api-Key = %q, want empty (sentinel stripped)", gotXApiKey)
	}
	if gotPath != "/v1/messages" {
		t.Errorf("upstream path = %q, want /v1/messages", gotPath)
	}
	if gotQuery != "beta=1" {
		t.Errorf("upstream query = %q, want beta=1", gotQuery)
	}
	if string(body) != "data: ok\n\n" {
		t.Errorf("body = %q", body)
	}
}

func TestBrokerJoinsUpstreamBasePath(t *testing.T) {
	var gotPath string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
	}))
	defer upstream.Close()

	sock := filepath.Join(t.TempDir(), "e.sock")
	b := New(nil)
	defer b.Stop()
	// Upstream has a /v1 base prefix (basic-agent style); incoming /chat/completions.
	if err := b.Add(EndpointEgress{
		Slug:       "basic",
		SocketPath: sock,
		Source:     fixedSource{cred: Credential{Upstream: upstream.URL + "/v1", Headers: map[string]string{"Authorization": "Bearer X"}}},
	}); err != nil {
		t.Fatalf("Add: %v", err)
	}

	resp, err := unixClient(sock).Get("http://broker/chat/completions")
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	resp.Body.Close()
	if gotPath != "/v1/chat/completions" {
		t.Errorf("upstream path = %q, want /v1/chat/completions", gotPath)
	}
}

func TestBrokerPerEndpointIsolation(t *testing.T) {
	var authA, authB string
	upA := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { authA = r.Header.Get("Authorization") }))
	defer upA.Close()
	upB := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { authB = r.Header.Get("Authorization") }))
	defer upB.Close()

	dir := t.TempDir()
	sockA := filepath.Join(dir, "a.sock")
	sockB := filepath.Join(dir, "b.sock")
	b := New(nil)
	defer b.Stop()
	_ = b.Add(EndpointEgress{Slug: "a", SocketPath: sockA, Source: fixedSource{cred: Credential{Upstream: upA.URL, Headers: map[string]string{"Authorization": "Bearer KEY_A"}}}})
	_ = b.Add(EndpointEgress{Slug: "b", SocketPath: sockB, Source: fixedSource{cred: Credential{Upstream: upB.URL, Headers: map[string]string{"Authorization": "Bearer KEY_B"}}}})

	if r, err := unixClient(sockA).Get("http://broker/x"); err == nil {
		r.Body.Close()
	} else {
		t.Fatalf("A: %v", err)
	}
	if r, err := unixClient(sockB).Get("http://broker/x"); err == nil {
		r.Body.Close()
	} else {
		t.Fatalf("B: %v", err)
	}
	if authA != "Bearer KEY_A" || authB != "Bearer KEY_B" {
		t.Errorf("isolation broken: authA=%q authB=%q", authA, authB)
	}
}

func TestBrokerMapsResolveErrors(t *testing.T) {
	dir := t.TempDir()
	cases := []struct {
		name string
		err  error
		want int
	}{
		{"expired", ErrCredentialExpired, http.StatusUnauthorized},
		{"missing", ErrNoCredential, http.StatusBadGateway},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			sock := filepath.Join(dir, c.name+".sock")
			b := New(nil)
			defer b.Stop()
			_ = b.Add(EndpointEgress{Slug: c.name, SocketPath: sock, Source: fixedSource{err: c.err}})
			resp, err := unixClient(sock).Get("http://broker/x")
			if err != nil {
				t.Fatalf("request: %v", err)
			}
			resp.Body.Close()
			if resp.StatusCode != c.want {
				t.Errorf("status = %d, want %d", resp.StatusCode, c.want)
			}
		})
	}
}

func TestBrokerReAddReplaces(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	defer up.Close()
	sock := filepath.Join(t.TempDir(), "e.sock")
	b := New(nil)
	defer b.Stop()
	src := fixedSource{cred: Credential{Upstream: up.URL, Headers: map[string]string{"Authorization": "Bearer X"}}}
	if err := b.Add(EndpointEgress{Slug: "e", SocketPath: sock, Source: src}); err != nil {
		t.Fatalf("first Add: %v", err)
	}
	// Re-Add the same slug must not fail on a stale socket file.
	if err := b.Add(EndpointEgress{Slug: "e", SocketPath: sock, Source: src}); err != nil {
		t.Fatalf("re-Add: %v", err)
	}
	if r, err := unixClient(sock).Get("http://broker/x"); err == nil {
		r.Body.Close()
	} else {
		t.Fatalf("after re-Add: %v", err)
	}
}
