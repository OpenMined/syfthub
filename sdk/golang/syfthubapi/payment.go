package syfthubapi

// PaymentMetadataKeys is the allow-list of policy-metadata keys that are safe
// to forward to the caller in a PAYMENT_REQUIRED response. Other policy
// metadata stays internal.
var PaymentMetadataKeys = []string{
	"payment_challenge",
	"payment_amount",
	"payment_currency",
	"payment_recipient",
	"challenge_id",
	"intent",
}

// PaymentChallengeFromMetadata returns the payment_challenge string from a
// policy-result metadata map, and true iff present and non-empty.
func PaymentChallengeFromMetadata(meta map[string]any) (string, bool) {
	if meta == nil {
		return "", false
	}
	s, ok := meta["payment_challenge"].(string)
	if !ok || s == "" {
		return "", false
	}
	return s, true
}

// CopyPaymentMetadata returns a copy of the safe payment_* keys from a policy
// metadata map. Returns nil when no safe keys are present.
func CopyPaymentMetadata(meta map[string]any) map[string]any {
	if meta == nil {
		return nil
	}
	var out map[string]any
	for _, k := range PaymentMetadataKeys {
		if v, ok := meta[k]; ok {
			if out == nil {
				out = make(map[string]any, len(PaymentMetadataKeys))
			}
			out[k] = v
		}
	}
	return out
}
