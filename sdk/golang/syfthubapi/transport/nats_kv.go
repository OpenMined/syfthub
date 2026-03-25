package transport

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// kvBucketName is the JetStream KV bucket for tracking active agent sessions.
const kvBucketName = "AGENT_SESSIONS"

// NATSSessionRegistry implements syfthubapi.SessionRegistrar using JetStream KV.
// It stores session metadata in a KV bucket so that admin tooling and external
// systems can observe active sessions, and TTL-based cleanup handles abandoned entries.
type NATSSessionRegistry struct {
	kv     nats.KeyValue
	logger *slog.Logger
}

// NewNATSSessionRegistry creates a session registry backed by a JetStream KV bucket.
// If JetStream is not available on the server, returns (nil, error) — the caller
// should treat this as a non-fatal condition and proceed without a registry.
func NewNATSSessionRegistry(conn *nats.Conn, logger *slog.Logger) (*NATSSessionRegistry, error) {
	js, err := conn.JetStream()
	if err != nil {
		return nil, fmt.Errorf("JetStream not available: %w", err)
	}

	// Create or bind to the KV bucket.
	kv, err := js.CreateKeyValue(&nats.KeyValueConfig{
		Bucket:      kvBucketName,
		Description: "Active agent session metadata for admin visibility and TTL cleanup",
		TTL:         2 * time.Hour,
		MaxBytes:    64 * 1024 * 1024, // 64 MiB max
		Storage:     nats.MemoryStorage,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create KV bucket %s: %w", kvBucketName, err)
	}

	logger.Info("[AGENT] JetStream KV session registry initialized", "bucket", kvBucketName)
	return &NATSSessionRegistry{kv: kv, logger: logger}, nil
}

// RegisterSession stores session metadata in the KV bucket.
func (r *NATSSessionRegistry) RegisterSession(meta syfthubapi.SessionMeta) error {
	data, err := json.Marshal(meta)
	if err != nil {
		return fmt.Errorf("marshal session meta: %w", err)
	}
	_, err = r.kv.Put(meta.SessionID, data)
	if err != nil {
		return fmt.Errorf("KV put session %s: %w", meta.SessionID, err)
	}
	r.logger.Debug("[AGENT] Session registered in KV", "session_id", meta.SessionID)
	return nil
}

// DeregisterSession removes session metadata from the KV bucket.
func (r *NATSSessionRegistry) DeregisterSession(sessionID string) error {
	err := r.kv.Delete(sessionID)
	if err != nil {
		return fmt.Errorf("KV delete session %s: %w", sessionID, err)
	}
	r.logger.Debug("[AGENT] Session deregistered from KV", "session_id", sessionID)
	return nil
}
