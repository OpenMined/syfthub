package transport

import (
	"context"
	"errors"
	"fmt"
	"io"
	"sync"
	"time"

	"github.com/nats-io/nats.go"
)

// AttachmentBucketPrefix is the JetStream Object Store bucket name prefix
// for attachment ciphertext blobs. The full bucket name is
// AttachmentBucketPrefix + session_id.
const AttachmentBucketPrefix = "syft-att-"

// DefaultAttachmentBucketTTL is the default bucket-level retention after
// which a bucket may be reaped. The aggregator should explicitly delete
// per-session buckets in its session cleanup, but the TTL is the
// belt-and-suspenders defense.
const DefaultAttachmentBucketTTL = 1 * time.Hour

// AttachmentObjectStore is the interface the encrypted-attachment transport
// uses to persist ciphertext blobs. The production implementation is
// NATSAttachmentObjectStore (JetStream Object Store); an in-memory test
// fixture lives in attachment_object_store_memory_test.go.
type AttachmentObjectStore interface {
	// EnsureBucket creates the named bucket if it doesn't already exist.
	// ttl is the per-object retention. Idempotent.
	EnsureBucket(ctx context.Context, bucket string, ttl time.Duration) error

	// Put streams ciphertext into the bucket under the given key.
	Put(ctx context.Context, bucket, key string, r io.Reader) error

	// Get streams ciphertext for (bucket, key) to w.
	Get(ctx context.Context, bucket, key string, w io.Writer) error

	// DeleteBucket removes the bucket and all its objects. Idempotent.
	DeleteBucket(ctx context.Context, bucket string) error
}

// bucketNameForSession composes the standard bucket name for a session.
func bucketNameForSession(sessionID string) string {
	return AttachmentBucketPrefix + sessionID
}

// NATSAttachmentObjectStore implements AttachmentObjectStore against a
// JetStream Object Store.
type NATSAttachmentObjectStore struct {
	js nats.JetStreamContext
	mu sync.Mutex
	// cached object stores by bucket name to avoid re-binding on every call
	stores map[string]nats.ObjectStore
}

// NewNATSAttachmentObjectStore binds an Object Store-backed store to an
// existing JetStream context.
func NewNATSAttachmentObjectStore(conn *nats.Conn) (*NATSAttachmentObjectStore, error) {
	js, err := conn.JetStream()
	if err != nil {
		return nil, fmt.Errorf("JetStream: %w", err)
	}
	return &NATSAttachmentObjectStore{js: js, stores: map[string]nats.ObjectStore{}}, nil
}

// EnsureBucket creates the Object Store bucket if it doesn't yet exist.
func (s *NATSAttachmentObjectStore) EnsureBucket(_ context.Context, bucket string, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.stores[bucket]; ok {
		return nil
	}
	if ttl <= 0 {
		ttl = DefaultAttachmentBucketTTL
	}
	os, err := s.js.ObjectStore(bucket)
	if err == nil {
		s.stores[bucket] = os
		return nil
	}
	if !errors.Is(err, nats.ErrStreamNotFound) {
		// Best-effort: try to create regardless of the surfaced error.
		// JetStream returns generic errors when the underlying stream
		// doesn't exist; we accept and try to create.
	}
	os, err = s.js.CreateObjectStore(&nats.ObjectStoreConfig{
		Bucket:      bucket,
		Description: "SyftHub attachment ciphertext (per-session)",
		TTL:         ttl,
		Storage:     nats.FileStorage,
	})
	if err != nil {
		return fmt.Errorf("create bucket %s: %w", bucket, err)
	}
	s.stores[bucket] = os
	return nil
}

func (s *NATSAttachmentObjectStore) getStore(bucket string) (nats.ObjectStore, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if os, ok := s.stores[bucket]; ok {
		return os, nil
	}
	os, err := s.js.ObjectStore(bucket)
	if err != nil {
		return nil, fmt.Errorf("bind bucket %s: %w", bucket, err)
	}
	s.stores[bucket] = os
	return os, nil
}

// Put streams from r into the named object using the JetStream chunked
// streaming API.
func (s *NATSAttachmentObjectStore) Put(_ context.Context, bucket, key string, r io.Reader) error {
	os, err := s.getStore(bucket)
	if err != nil {
		return err
	}
	if _, err := os.Put(&nats.ObjectMeta{Name: key}, r); err != nil {
		return fmt.Errorf("put %s/%s: %w", bucket, key, err)
	}
	return nil
}

// Get streams the named object to w.
func (s *NATSAttachmentObjectStore) Get(_ context.Context, bucket, key string, w io.Writer) error {
	os, err := s.getStore(bucket)
	if err != nil {
		return err
	}
	rc, err := os.Get(key)
	if err != nil {
		return fmt.Errorf("get %s/%s: %w", bucket, key, err)
	}
	defer rc.Close()
	if _, err := io.Copy(w, rc); err != nil {
		return fmt.Errorf("stream %s/%s: %w", bucket, key, err)
	}
	return nil
}

// DeleteBucket removes the bucket and all its objects.
func (s *NATSAttachmentObjectStore) DeleteBucket(_ context.Context, bucket string) error {
	s.mu.Lock()
	delete(s.stores, bucket)
	s.mu.Unlock()
	return s.js.DeleteObjectStore(bucket)
}
