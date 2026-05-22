package mppxgate

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/mppx"
)

// Metadata keys the gate reads from / writes to the policy-result and
// request-context metadata maps. Kept here (rather than as magic strings
// scattered through the file) so the contract with the Python policy is
// reviewable in one place.
const (
	// Spec key the Python policy writes on round 1 (challenge needed).
	MetaKeyChallengeSpec = "x402_challenge_spec"

	// Keys the gate writes after BuildChallenge — what the caller needs to
	// build a credential.
	MetaKeyPaymentChallenge = "payment_challenge"
	MetaKeyPaymentAmount    = "payment_amount"
	MetaKeyPaymentCurrency  = "payment_currency"
	MetaKeyPaymentRecipient = "payment_recipient"
	MetaKeyChallengeID      = "challenge_id"

	// Keys the gate writes after a successful PreVerify — what the Python
	// policy reads on round 2 to short-circuit pre_execute.
	MetaKeyPaymentVerified    = "payment_verified"
	MetaKeyPaymentChallengeID = "payment_challenge_id"
	MetaKeyPaymentNonce       = "payment_nonce"

	// Internal handoff between PreVerify (verifies + parks the signed tx)
	// and SettleAfterHandler (broadcasts it on handler success). Never
	// crosses the wire to the caller.
	MetaKeyPaymentSignedTxHex = "payment_signed_tx_hex"

	// Keys the gate writes after SettleAfterHandler so the Python policy's
	// post_execute can record settlement.
	MetaKeyPaymentReceipt = "payment_receipt"
	MetaKeyPaymentStatus  = "payment_status"
	MetaKeyPaymentFailure = "payment_failure"
)

// Spec keys produced by the Python policy.
const (
	specKeyPayTo         = "pay_to"
	specKeyCurrency      = "currency"
	specKeyDecimals      = "decimals"
	specKeyChainID       = "chain_id"
	specKeyAmount        = "amount"
	specKeyRealm         = "realm"
	specKeyExpiresAtISO  = "expires_at_iso"
	specKeyHmacSecretKid = "hmac_secret_kid"
)

// defaultClockSkew is the verifier-side tolerance for clock drift between
// signer and verifier. Mirrors the value used by the model client.
const defaultClockSkew = 30 * time.Second

// Gate is the interface the syfthubapi RequestProcessor uses to drive the
// x402 settle-on-success flow. The implementation lives in this package
// (TempoGate); the interface is mirrored as syfthubapi.MppxGate so the
// processor can hold it without importing this package back.
//
// The contract with the Python X402PayPerRequestPolicy is documented in
// the package-level comment; see also the constants above for the exact
// metadata keys exchanged.
type Gate interface {
	// PreVerify verifies a presented payment credential against the in-flight
	// charge challenge, recovers the on-chain sender, parks the signed
	// transaction bytes in metadata for later broadcast, and flips the
	// payment_verified flag so the Python policy short-circuits on its
	// second pre_execute. Returns an error when the credential is missing
	// or invalid — callers MUST log and continue (the Python policy will
	// then return a fresh challenge spec).
	PreVerify(ctx context.Context, credential string, metadata map[string]any) error

	// BuildChallenge materializes an HMAC-bound mppx Challenge from the
	// Python-supplied spec and writes the canonical payment_challenge wire
	// string + supporting fields (amount, currency, recipient, challenge_id)
	// into resultMeta. The spec carries the kid; the secret itself is
	// looked up via the configured SecretStore.
	BuildChallenge(ctx context.Context, spec map[string]any, resultMeta map[string]any) error

	// SettleAfterHandler broadcasts the previously-verified signed transfer
	// (parked under MetaKeyPaymentSignedTxHex) to the network and writes
	// the receipt + status into metadata for the Python post_execute. It
	// is a no-op when no signed tx is parked (e.g. an allow-listed payer
	// or a request that never required payment).
	SettleAfterHandler(ctx context.Context, metadata map[string]any) error
}

// TempoGate is the Tempo/USDC implementation of Gate. It is safe for
// concurrent use; per-payer serialization of broadcasts keeps two
// concurrent settles from racing on the same payer's nonce slot.
type TempoGate struct {
	rpcURL    string
	clockSkew time.Duration
	secrets   SecretStore
	logger    *slog.Logger

	// payerMu serialises broadcasts per-payer (address hex). Without it,
	// two concurrent requests from the same wallet could broadcast in the
	// wrong order — the second tx would race on the same nonce slot and
	// fail with "nonce too low" on the RPC side. Per-payer (not global)
	// because distinct payers have distinct nonce sequences.
	payerMu sync.Map // map[string]*sync.Mutex

	// kidLookup remembers which kid produced each challenge ID so PreVerify
	// can look up the right HMAC secret on round 2. Per-gate (not package-
	// global) so multiple TempoGates (e.g. with distinct SecretStores) do
	// not collide. Entries live until the process restarts; bounded in
	// practice by the desktop's per-user challenge rate.
	kidLookup sync.Map // map[challengeID]kid
}

// TempoGateOptions configures a TempoGate.
type TempoGateOptions struct {
	// RPCURL is the Tempo JSON-RPC endpoint used to fetch the latest nonce
	// during PreVerify and to broadcast on SettleAfterHandler. Required.
	RPCURL string

	// Secrets is the keystore the gate uses to look up HMAC secrets by
	// kid. Required.
	Secrets SecretStore

	// ClockSkew is the tolerance applied when checking challenge expiry.
	// Defaults to defaultClockSkew when zero.
	ClockSkew time.Duration

	// Logger is the structured logger. Defaults to slog.Default when nil.
	Logger *slog.Logger
}

// NewTempoGate builds a TempoGate from opts. Returns an error when a
// required option is missing.
func NewTempoGate(opts TempoGateOptions) (*TempoGate, error) {
	if opts.RPCURL == "" {
		return nil, errors.New("mppxgate: RPCURL is required")
	}
	if opts.Secrets == nil {
		return nil, errors.New("mppxgate: Secrets is required")
	}
	skew := opts.ClockSkew
	if skew == 0 {
		skew = defaultClockSkew
	}
	logger := opts.Logger
	if logger == nil {
		logger = slog.Default()
	}
	return &TempoGate{
		rpcURL:    opts.RPCURL,
		clockSkew: skew,
		secrets:   opts.Secrets,
		logger:    logger,
	}, nil
}

// PreVerify implements Gate.
func (g *TempoGate) PreVerify(ctx context.Context, credential string, metadata map[string]any) error {
	if credential == "" {
		return errors.New("mppxgate: empty credential")
	}
	if metadata == nil {
		return errors.New("mppxgate: nil metadata map")
	}
	cred, err := mppx.DeserializeCredential(credential)
	if err != nil {
		return fmt.Errorf("mppxgate: deserialize credential: %w", err)
	}
	// Resolve the HMAC secret from the kid embedded in the echoed challenge's
	// realm? The kid is carried in the opaque field on the wire — but the
	// echoed challenge in the credential lacks any kid hint. Instead we
	// derive it from the embedded request: the spec puts the kid into the
	// challenge.request methodDetails when BuildChallenge runs. If that
	// fails, fall back to "default".
	kid := g.extractKidFromChallenge(cred.Challenge)
	secret, err := g.secrets.Get(kid)
	if err != nil {
		return fmt.Errorf("mppxgate: lookup secret %q: %w", kid, err)
	}

	parsed, _, err := mppx.VerifySignedTransferCredential(ctx, cred, secret, g.rpcURL, g.clockSkew)
	if err != nil {
		return fmt.Errorf("mppxgate: verify credential: %w", err)
	}

	// The verified payload carries the signed-tx bytes we need to broadcast
	// later. Pull them out of the echoed payload (decodeSignedTransferPayload
	// is unexported in mppx; the payload field on a freshly-deserialised
	// credential is map[string]any).
	signedTxHex, nonce, payer, err := extractSignedTxFields(cred.Payload)
	if err != nil {
		return fmt.Errorf("mppxgate: extract signed tx: %w", err)
	}

	g.logger.Info("[X402] credential verified",
		"challenge_id", cred.Challenge.ID,
		"payer", payer,
		"amount", parsed.Amount.String(),
		"nonce", nonce,
	)

	metadata[MetaKeyPaymentVerified] = true
	metadata[MetaKeyPaymentChallengeID] = cred.Challenge.ID
	metadata[MetaKeyPaymentNonce] = nonce
	metadata[MetaKeyPaymentSignedTxHex] = signedTxHex
	// Internal-only: stash payer so SettleAfterHandler can pick the right
	// mutex without re-parsing the tx.
	metadata[metaKeyPaymentPayerInternal] = payer
	return nil
}

// BuildChallenge implements Gate.
func (g *TempoGate) BuildChallenge(ctx context.Context, spec map[string]any, resultMeta map[string]any) error {
	if spec == nil {
		return errors.New("mppxgate: nil spec")
	}
	if resultMeta == nil {
		return errors.New("mppxgate: nil result metadata map")
	}

	payTo, err := stringField(spec, specKeyPayTo)
	if err != nil {
		return err
	}
	currency, err := stringField(spec, specKeyCurrency)
	if err != nil {
		return err
	}
	amount, err := stringField(spec, specKeyAmount)
	if err != nil {
		return err
	}
	realm, err := stringField(spec, specKeyRealm)
	if err != nil {
		return err
	}
	chainID, err := intField(spec, specKeyChainID)
	if err != nil {
		return err
	}
	// Decimals is declared in the spec but the amount is already in base
	// units (see _amount_base_units in the Python policy); we don't need
	// to apply decimals again. Read it for validation only — a non-int
	// value would mean the spec is malformed.
	if _, err := intField(spec, specKeyDecimals); err != nil {
		return err
	}

	kid := "default"
	if k, ok := spec[specKeyHmacSecretKid].(string); ok && k != "" {
		kid = k
	}
	secret, err := g.secrets.Get(kid)
	if err != nil {
		return fmt.Errorf("mppxgate: lookup secret %q: %w", kid, err)
	}

	expires := time.Now().UTC().Add(mppx.DefaultExpiry)
	if expStr, ok := spec[specKeyExpiresAtISO].(string); ok && expStr != "" {
		if t, perr := parseISO(expStr); perr == nil {
			expires = t
		} else {
			g.logger.Warn("[X402] failed to parse expires_at_iso; falling back to default",
				"value", expStr, "error", perr)
		}
	}

	// The amount in the spec is already in base units (Python encodes it via
	// _amount_base_units). mppx.NewCharge expects a human-readable decimal
	// string and re-applies decimals — so feed it the integer string with
	// Decimals(0) to keep the conversion a no-op.
	challenge, err := mppx.NewCharge(currency, payTo, chainID).
		Amount(amount).
		Decimals(0).
		Realm(realm).
		ExpiresAt(expires).
		WithSecretKey(secret).
		Build()
	if err != nil {
		return fmt.Errorf("mppxgate: build challenge: %w", err)
	}

	// Embed the kid in methodDetails so PreVerify can recover it from the
	// echoed challenge on round 2. Done after Build (so the kid does NOT
	// participate in the HMAC) is wrong — the HMAC must cover the kid or
	// a tampering peer could swap kids freely. Instead we'd need to either
	// bind kid into the spec before HMAC, or persist the (challenge_id,kid)
	// pair on the gate. We chose persistence: see kidLookupTable.
	g.rememberKid(challenge.ID, kid)

	wire, err := mppx.SerializeChallenge(challenge)
	if err != nil {
		return fmt.Errorf("mppxgate: serialize challenge: %w", err)
	}

	resultMeta[MetaKeyPaymentChallenge] = wire
	resultMeta[MetaKeyPaymentAmount] = amount
	resultMeta[MetaKeyPaymentCurrency] = currency
	resultMeta[MetaKeyPaymentRecipient] = payTo
	resultMeta[MetaKeyChallengeID] = challenge.ID

	g.logger.Info("[X402] challenge built",
		"challenge_id", challenge.ID,
		"realm", realm,
		"amount", amount,
		"recipient", payTo,
	)
	_ = ctx // reserved for future cancellable paths
	return nil
}

// SettleAfterHandler implements Gate.
//
// Post-condition (relied on by the syfthubapi processor's post-execute
// round-trip): on both the success and broadcast-failure paths the
// metadata map carries MetaKeyPaymentChallengeID and MetaKeyPaymentNonce
// — both written by PreVerify and never cleared here — so the Python
// X402PayPerRequestPolicy.post_execute can locate the x402_transactions
// row by its primary key (the canonical challenge id).
func (g *TempoGate) SettleAfterHandler(ctx context.Context, metadata map[string]any) error {
	if metadata == nil {
		return nil
	}
	signedTxHex, ok := metadata[MetaKeyPaymentSignedTxHex].(string)
	if !ok || signedTxHex == "" {
		// No payment was held for this request — nothing to settle.
		return nil
	}

	payer, _ := metadata[metaKeyPaymentPayerInternal].(string)
	if payer != "" {
		mu := g.payerLock(payer)
		mu.Lock()
		defer mu.Unlock()
	}

	// Defensive: PreVerify writes payment_challenge_id when it parks the
	// signed tx; if for any reason it is missing here the Python
	// post_execute would silently no-op (its row lookup is keyed on this
	// id). Warn rather than fail — the broadcast itself can still succeed.
	if cid, _ := metadata[MetaKeyPaymentChallengeID].(string); cid == "" {
		g.logger.Warn("[X402] settle running without payment_challenge_id in metadata; post_execute will skip row update",
			"payer", payer,
		)
	}

	receipt, err := mppx.BroadcastSignedTransfer(ctx, signedTxHex, g.rpcURL)
	if err != nil {
		g.logger.Error("[X402] broadcast failed", "error", err, "payer", payer)
		metadata[MetaKeyPaymentFailure] = map[string]any{"reason": err.Error()}
		metadata[MetaKeyPaymentStatus] = "failed"
		// Wipe the signed-tx so a caller-level retry cannot accidentally
		// re-broadcast the same bytes; the payer must re-sign.
		delete(metadata, MetaKeyPaymentSignedTxHex)
		return err
	}

	g.logger.Info("[X402] payment settled",
		"payer", payer,
		"tx_hash", receipt.Reference,
		"status", receipt.Status,
	)
	metadata[MetaKeyPaymentReceipt] = map[string]any{
		"method":    receipt.Method,
		"reference": receipt.Reference,
		"status":    receipt.Status,
		"timestamp": receipt.Timestamp.UTC().Format(time.RFC3339Nano),
	}
	metadata[MetaKeyPaymentStatus] = receipt.Status
	// Settlement consumed the signed-tx; drop it so it cannot be re-played.
	delete(metadata, MetaKeyPaymentSignedTxHex)
	return nil
}

// payerLock returns the mutex serialising broadcasts for a payer address.
// Mutexes are allocated on first use and kept alive for the gate's lifetime
// — there is no eviction, but the map size is bounded by the number of
// distinct payers the desktop ever sees, which is small.
func (g *TempoGate) payerLock(payer string) *sync.Mutex {
	if existing, ok := g.payerMu.Load(payer); ok {
		return existing.(*sync.Mutex)
	}
	mu := &sync.Mutex{}
	actual, _ := g.payerMu.LoadOrStore(payer, mu)
	return actual.(*sync.Mutex)
}

// ── kid handoff ─────────────────────────────────────────────────────────────
//
// The kid is the lookup key Python passes to BuildChallenge but cannot embed
// in the HMAC-signed challenge (the HMAC covers method/intent/request only;
// adding a custom field would break the cross-language wire format). So we
// remember kids server-side, keyed by the canonical challenge id. The map
// is bounded — challenges live ~5min and the desktop sees a single user.
//
// On PreVerify we look up by challenge id; if absent (e.g. a challenge built
// before the process restarted) we fall back to the kid embedded in the
// echoed request's methodDetails.kid, then to "default".

const metaKeyPaymentPayerInternal = "_x402_payer_internal"

func (g *TempoGate) rememberKid(challengeID, kid string) {
	if challengeID == "" || kid == "" {
		return
	}
	g.kidLookup.Store(challengeID, kid)
}

// extractKidFromChallenge recovers the kid that produced challenge.ID.
// Lookup order: per-gate kid table → methodDetails.kid on the echoed
// request → "default".
func (g *TempoGate) extractKidFromChallenge(c mppx.Challenge) string {
	if v, ok := g.kidLookup.Load(c.ID); ok {
		if kid, ok := v.(string); ok && kid != "" {
			return kid
		}
	}
	if md, ok := c.Request["methodDetails"].(map[string]any); ok {
		if kid, ok := md["kid"].(string); ok && kid != "" {
			return kid
		}
	}
	return "default"
}

// extractSignedTxFields pulls (signed_tx, nonce, from) from a freshly-
// deserialised credential payload. The payload arrives as map[string]any
// (DeserializeCredential uses encoding/json with UseNumber).
func extractSignedTxFields(payload any) (signedTx string, nonce uint64, from string, err error) {
	m, ok := payload.(map[string]any)
	if !ok {
		// Could already be a typed struct (in-process path).
		if p, ok := payload.(mppx.TempoSignedTransferPayload); ok {
			return p.SignedTx, p.Nonce, p.From, nil
		}
		return "", 0, "", fmt.Errorf("unexpected payload type %T", payload)
	}
	if s, ok := m["signed_tx"].(string); ok {
		signedTx = s
	}
	if s, ok := m["from"].(string); ok {
		from = s
	}
	switch n := m["nonce"].(type) {
	case json.Number:
		i, err := n.Int64()
		if err != nil {
			return "", 0, "", fmt.Errorf("invalid nonce: %w", err)
		}
		nonce = uint64(i)
	case float64:
		nonce = uint64(n)
	case int:
		nonce = uint64(n)
	case int64:
		nonce = uint64(n)
	case uint64:
		nonce = n
	case string:
		i, perr := strconv.ParseUint(n, 10, 64)
		if perr != nil {
			return "", 0, "", fmt.Errorf("invalid nonce string %q: %w", n, perr)
		}
		nonce = i
	}
	if signedTx == "" {
		return "", 0, "", errors.New("payload missing signed_tx")
	}
	return signedTx, nonce, from, nil
}

// stringField extracts a required string spec field.
func stringField(spec map[string]any, key string) (string, error) {
	v, ok := spec[key]
	if !ok {
		return "", fmt.Errorf("mppxgate: spec missing %q", key)
	}
	s, ok := v.(string)
	if !ok || s == "" {
		return "", fmt.Errorf("mppxgate: spec %q is not a non-empty string", key)
	}
	return s, nil
}

// intField extracts an int spec field tolerating JSON-decoded numeric forms.
func intField(spec map[string]any, key string) (int, error) {
	v, ok := spec[key]
	if !ok {
		return 0, fmt.Errorf("mppxgate: spec missing %q", key)
	}
	switch n := v.(type) {
	case int:
		return n, nil
	case int64:
		return int(n), nil
	case float64:
		return int(n), nil
	case json.Number:
		i, err := n.Int64()
		if err != nil {
			return 0, fmt.Errorf("mppxgate: spec %q: %w", key, err)
		}
		return int(i), nil
	case string:
		i, err := strconv.Atoi(n)
		if err != nil {
			return 0, fmt.Errorf("mppxgate: spec %q: %w", key, err)
		}
		return i, nil
	}
	return 0, fmt.Errorf("mppxgate: spec %q is not numeric (got %T)", key, v)
}

// parseISO parses an ISO 8601 / RFC 3339 timestamp the Python policy emits
// via datetime.isoformat(). Accepts both second and microsecond precision.
func parseISO(s string) (time.Time, error) {
	for _, layout := range []string{
		time.RFC3339Nano,
		time.RFC3339,
		"2006-01-02T15:04:05.000000-07:00",
		"2006-01-02T15:04:05.000-07:00",
		"2006-01-02T15:04:05",
	} {
		if t, err := time.Parse(layout, s); err == nil {
			return t.UTC(), nil
		}
	}
	return time.Time{}, fmt.Errorf("invalid timestamp %q", s)
}
