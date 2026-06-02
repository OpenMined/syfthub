package manualreview

import "time"

// ProtocolVersion is the on-wire protocol identifier for manual-review
// resolution envelopes. New schemes must use a new version string so an
// older client that decodes a future envelope can fail fast.
const ProtocolVersion = "syfthub-mr-v1"

// Message types carried in ResolvedEnvelope.Type. Only one type exists today;
// the field is present so receivers can fail-closed on unknown types instead
// of treating them as the resolution payload.
const (
	MsgTypeResolved = "manual_review_resolved"
)

// ResolutionStatus values mirror the manual_reviews.status column produced by
// the Python policy (policy_manager.policies.manual_review). "pending" is not
// a terminal state and is never carried on a resolved envelope; it is listed
// here only for symmetry with the host-side schema.
const (
	StatusPending  = "pending"
	StatusApproved = "approved"
	StatusRejected = "rejected"
)

// InboxSubjectPrefix is the NATS/JetStream subject prefix for per-recipient
// resolution inboxes. The full subject is InboxSubjectPrefix + username +
// ".review", e.g. "syfthub.inbox.alice.review". This is intentionally kept
// distinct from the v2 session subjects ("syfthub.spaces.*", "syfthub.peer.*")
// so deployments can route, store, and ACL them separately.
const InboxSubjectPrefix = "syfthub.inbox."

// InboxSubjectSuffix is appended after the username segment.
const InboxSubjectSuffix = ".review"

// InboxSubjectFor returns the resolution-inbox NATS subject for username.
// The caller MUST validate username before calling this — invalid usernames
// produce subjects that other tenants could subscribe to.
func InboxSubjectFor(username string) string {
	return InboxSubjectPrefix + username + InboxSubjectSuffix
}

// HKDFInfo is the domain-separation label fed to HKDF when deriving the
// resolution cipher key. Changing it invalidates every key derived under the
// old label, so a bump constitutes a new ProtocolVersion.
const HKDFInfo = "syfthub-mr-resolution-v1"

// ISOMicroLayout is the timestamp format that matches what policy_manager
// writes for manual_reviews.{submitted_at,resolved_at}. It is part of the
// on-wire contract carried by ResolvedPayload.ResolvedAt — every component
// that stamps a manual-review timestamp MUST use this layout.
const ISOMicroLayout = "2006-01-02T15:04:05.000000-07:00"

// NowISO returns the current UTC time formatted with ISOMicroLayout.
// Use this everywhere a manual-review timestamp is stamped so the layout
// is never accidentally swapped for a different format.
func NowISO() string { return time.Now().UTC().Format(ISOMicroLayout) }

// ResolvedEnvelope is the wire shape published to a recipient's inbox subject.
//
// Plaintext fields (Protocol through PolicyName) carry enough metadata for the
// receiver to dispatch the message without decrypting first — e.g. to fast-path
// it into a live AgentClientSession matched by SessionID, or to render a
// minimal entry on a fresh device that has never seen the original hold.
//
// The EncryptedPayload (sealed under the HKDFInfo-derived key) is the only
// channel for content the host considers sensitive: ResponseText (the real
// held output, on approval) and RejectReason (on rejection).
type ResolvedEnvelope struct {
	Protocol         string `json:"protocol"`  // = ProtocolVersion
	Type             string `json:"type"`      // = MsgTypeResolved
	ReviewID         string `json:"review_id"` // 12-hex handle, matches manual_reviews.review_id
	SessionID        string `json:"session_id,omitempty"`
	EndpointOwner    string `json:"endpoint_owner"`
	EndpointSlug     string `json:"endpoint_slug"`
	EndpointName     string `json:"endpoint_name,omitempty"`
	PolicyName       string `json:"policy_name,omitempty"`
	SenderPublicKey  string `json:"sender_public_key"` // host X25519 pubkey, base64url
	Nonce            string `json:"nonce"`             // base64
	EncryptedPayload string `json:"encrypted_payload"` // base64 ciphertext
}

// ResolvedPayload is the plaintext shape of an encrypted resolution. It
// matches the manual_reviews row state after _resolve has run on the host.
//
// ResponseText is populated for approvals and carries the placeholder-bypassed
// real handler output (a string for model/agent endpoints; JSON-pretty for
// data_source document lists). RejectReason is populated for rejections.
// They are never both populated.
type ResolvedPayload struct {
	ReviewID       string `json:"review_id"`
	Status         string `json:"status"`      // StatusApproved | StatusRejected
	ResolvedAt     string `json:"resolved_at"` // ISO-8601 UTC, formatted with ISOMicroLayout
	ResponseText   string `json:"response_text,omitempty"`
	RejectReason   string `json:"reject_reason,omitempty"`
	ResolverUserID string `json:"resolver_user_id,omitempty"`
}
