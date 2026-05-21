// Package manualreview implements the transport + persistence concerns for
// returning a manual-review resolution from an endpoint host back to the
// caller after the human (or callback) approves or rejects a held request.
//
// The policy itself (ManualReviewPolicy, defined in the policy-manager Python
// repo) is intentionally unaware of any of this. It writes the held request
// to the manual_reviews table and substitutes the response body with a
// placeholder. Everything in this package handles what happens AFTER that:
//
//   - Capture: when AgentExecutor surfaces a pending policy notice, a sibling
//     row is written to manual_review_routing keyed by review_id, recording
//     enough metadata (caller pubkey, inbox subject, original session_id,
//     peer_channel) to deliver the resolution later — even if the original
//     v2 agent session ended hours earlier.
//
//   - Deliver: on the host, when the desktop owner approves or rejects the
//     held request, the resolution payload (the real handler output for an
//     approval, the rejection reason otherwise) is encrypted under a key
//     derived from the caller's identity pubkey and the review_id, then
//     published to a durable JetStream subject scoped to the caller.
//
//   - Receive: on the caller's desktop, a long-running consumer of that
//     subject decrypts each envelope, updates the local sent_reviews ledger
//     with status_source="queried", and emits a UI event.
//
// The encryption scheme mirrors transport/crypto_session.go's pattern but
// uses review_id (not session_id) as the HKDF salt and a distinct "-v1"
// domain label so resolution keys cannot collide with v2 session keys:
//
//	shared = X25519(host_identity_priv, caller_identity_pub)
//	key    = HKDF-SHA256(shared, salt=review_id, info="syfthub-mr-resolution-v1")
//
// See agent_executor.go for the capture path, manual_review_operations.go
// (in syfthub-desktop) for the deliver path, and review_inbox_listener.go
// for the receive path.
package manualreview
