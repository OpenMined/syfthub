package syfthub

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// stubAggregator emulates the Python aggregator's POST/GET attachment
// endpoints just enough to verify the Go CLIENT SDK's HTTP transport.
type stubAggregator struct {
	mu       sync.Mutex
	uploads  map[string][]byte
	uploadAt map[string]string // file_id → name
}

func newStubAggregator() *stubAggregator {
	return &stubAggregator{
		uploads:  map[string][]byte{},
		uploadAt: map[string]string{},
	}
}

func (s *stubAggregator) httpServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/agent/session/", s.routeAttachment)
	return httptest.NewServer(mux)
}

func (s *stubAggregator) routeAttachment(w http.ResponseWriter, r *http.Request) {
	// path shape: /api/v1/agent/session/{sid}/attachment[/{fid}]
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	// ["api", "v1", "agent", "session", "{sid}", "attachment", ...]
	if len(parts) < 6 || parts[5] != "attachment" {
		http.NotFound(w, r)
		return
	}
	switch r.Method {
	case http.MethodPost:
		s.handleUpload(w, r)
	case http.MethodGet:
		if len(parts) < 7 {
			http.NotFound(w, r)
			return
		}
		s.handleDownload(w, r, parts[6])
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (s *stubAggregator) handleUpload(w http.ResponseWriter, r *http.Request) {
	ct := r.Header.Get("Content-Type")
	_, params, err := mime.ParseMediaType(ct)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	mr := multipart.NewReader(r.Body, params["boundary"])
	part, err := mr.NextPart()
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	defer part.Close()
	body, err := io.ReadAll(part)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if len(body) == 0 {
		http.Error(w, "empty", http.StatusBadRequest)
		return
	}
	fileID := "att-stub-" + strings.TrimPrefix(part.FileName(), "")

	s.mu.Lock()
	s.uploads[fileID] = body
	s.uploadAt[fileID] = part.FileName()
	s.mu.Unlock()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"file_id":    fileID,
		"name":       part.FileName(),
		"size_bytes": len(body),
	})
}

func (s *stubAggregator) handleDownload(w http.ResponseWriter, r *http.Request, fileID string) {
	s.mu.Lock()
	body, ok := s.uploads[fileID]
	s.mu.Unlock()
	if !ok {
		http.NotFound(w, r)
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(body)
}

func TestSendAttachmentDispatchesOverHTTPWhenOversize(t *testing.T) {
	stub := newStubAggregator()
	srv := stub.httpServer(t)
	defer srv.Close()

	// A minimal AgentSessionClient — no WS needed for the HTTP path.
	c := &AgentSessionClient{
		SessionID:         "sess-1",
		AggregatorHTTPURL: srv.URL,
	}

	body := make([]byte, InlineAttachmentMaxBytes+1024)
	for i := range body {
		body[i] = byte(i % 251)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	fileID, err := c.SendAttachment(ctx, bytes.NewReader(body), AttachmentOpts{
		Name: "blob.bin",
		MIME: "application/octet-stream",
	})
	if err != nil {
		t.Fatalf("SendAttachment: %v", err)
	}
	if !strings.HasPrefix(fileID, "att-") {
		t.Fatalf("file_id missing prefix: %q", fileID)
	}

	// Verify the stub received the full payload.
	stub.mu.Lock()
	got := stub.uploads[fileID]
	stub.mu.Unlock()
	if !bytes.Equal(got, body) {
		t.Fatalf("uploaded bytes drift: got %d bytes, want %d", len(got), len(body))
	}
}

func TestDownloadAttachmentRoundTrip(t *testing.T) {
	stub := newStubAggregator()
	srv := stub.httpServer(t)
	defer srv.Close()

	c := &AgentSessionClient{
		SessionID:         "sess-dl",
		AggregatorHTTPURL: srv.URL,
	}

	// Pre-populate via SendAttachment over HTTP.
	body := bytes.Repeat([]byte("download me "), 10000) // ~120 KiB → HTTP path
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	fileID, err := c.SendAttachment(ctx, bytes.NewReader(body), AttachmentOpts{Name: "x.txt", MIME: "text/plain"})
	if err != nil {
		t.Fatal(err)
	}

	var out bytes.Buffer
	if err := c.DownloadAttachment(ctx, fileID, &out); err != nil {
		t.Fatalf("DownloadAttachment: %v", err)
	}
	if !bytes.Equal(out.Bytes(), body) {
		t.Fatal("downloaded bytes drift")
	}
}

func TestSendAttachmentHTTPMissingURLReturnsError(t *testing.T) {
	c := &AgentSessionClient{SessionID: "sess-no-url"}
	body := make([]byte, InlineAttachmentMaxBytes+1)
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()
	_, err := c.SendAttachment(ctx, bytes.NewReader(body), AttachmentOpts{})
	if err == nil {
		t.Fatal("expected error for missing AggregatorHTTPURL")
	}
}

func TestDownloadAttachmentMissingURLReturnsError(t *testing.T) {
	c := &AgentSessionClient{SessionID: "sess-no-url"}
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()
	if err := c.DownloadAttachment(ctx, "att-x", io.Discard); err == nil {
		t.Fatal("expected error for missing AggregatorHTTPURL")
	}
}
