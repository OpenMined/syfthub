package transport

import (
	"context"
	"fmt"
	"io"
	"sync"
	"time"
)

// MemoryAttachmentObjectStore is an in-process implementation of
// AttachmentObjectStore intended only for tests in this package. Production
// code uses NATSAttachmentObjectStore against a JetStream server.
type MemoryAttachmentObjectStore struct {
	mu      sync.Mutex
	buckets map[string]map[string][]byte
}

// NewMemoryAttachmentObjectStore returns a fresh in-memory store.
func NewMemoryAttachmentObjectStore() *MemoryAttachmentObjectStore {
	return &MemoryAttachmentObjectStore{buckets: map[string]map[string][]byte{}}
}

func (m *MemoryAttachmentObjectStore) EnsureBucket(_ context.Context, bucket string, _ time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.buckets[bucket]; !ok {
		m.buckets[bucket] = map[string][]byte{}
	}
	return nil
}

func (m *MemoryAttachmentObjectStore) Put(ctx context.Context, bucket, key string, r io.Reader) error {
	if err := m.EnsureBucket(ctx, bucket, 0); err != nil {
		return err
	}
	data, err := io.ReadAll(r)
	if err != nil {
		return fmt.Errorf("read: %w", err)
	}
	m.mu.Lock()
	m.buckets[bucket][key] = data
	m.mu.Unlock()
	return nil
}

func (m *MemoryAttachmentObjectStore) Get(_ context.Context, bucket, key string, w io.Writer) error {
	m.mu.Lock()
	b, ok := m.buckets[bucket]
	if !ok {
		m.mu.Unlock()
		return fmt.Errorf("bucket %q not found", bucket)
	}
	data, ok := b[key]
	m.mu.Unlock()
	if !ok {
		return fmt.Errorf("key %q not found in bucket %q", key, bucket)
	}
	if _, err := w.Write(data); err != nil {
		return fmt.Errorf("write: %w", err)
	}
	return nil
}

func (m *MemoryAttachmentObjectStore) Delete(_ context.Context, bucket, key string) error {
	m.mu.Lock()
	if b, ok := m.buckets[bucket]; ok {
		delete(b, key)
	}
	m.mu.Unlock()
	return nil
}

func (m *MemoryAttachmentObjectStore) DeleteBucket(_ context.Context, bucket string) error {
	m.mu.Lock()
	delete(m.buckets, bucket)
	m.mu.Unlock()
	return nil
}
