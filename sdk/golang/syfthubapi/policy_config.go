package syfthubapi

import "github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"

// PolicyConfig is a type alias for nodeops.Policy, the canonical definition.
// Both types share identical fields and JSON/YAML tags.
// This matches the Python policy_manager.runner.schema.PolicyConfigSchema.
type PolicyConfig = nodeops.Policy

// StoreConfig represents storage configuration for stateful policies.
// This matches the Python policy_manager.runner.schema.StoreConfigSchema.
type StoreConfig struct {
	// Type is the store type ("memory" or "sqlite").
	Type string `yaml:"type" json:"type"`

	// Path is the path to SQLite database file (for sqlite type).
	Path string `yaml:"path" json:"path"`
}

// ExecutionContext contains request context passed to Python runner.
// This matches the Python policy_manager.runner.schema.ExecutionContextSchema.
type ExecutionContext struct {
	// UserID is the authenticated user identifier.
	UserID string `json:"user_id"`

	// EndpointSlug is the target endpoint slug.
	EndpointSlug string `json:"endpoint_slug"`

	// EndpointType is the endpoint type ("model" or "data_source").
	EndpointType string `json:"endpoint_type"`

	// Metadata contains additional context metadata.
	Metadata map[string]any `json:"metadata,omitempty"`
}

// PolicyResultOutput represents policy evaluation result from Python runner.
// This matches the Python policy_manager.runner.schema.PolicyResultSchema.
type PolicyResultOutput struct {
	// Allowed indicates whether the policy chain allowed the request.
	Allowed bool `json:"allowed"`

	// PolicyName is the name of the policy that made the decision.
	PolicyName string `json:"policy_name,omitempty"`

	// Reason is a human-readable explanation (for denials).
	Reason string `json:"reason,omitempty"`

	// Pending indicates whether the request is pending async resolution.
	Pending bool `json:"pending"`

	// Metadata contains additional policy-specific metadata.
	Metadata map[string]any `json:"metadata,omitempty"`
}

// Known policy types for validation.
const (
	PolicyTypeAccessGroup        = "access_group"
	PolicyTypeRateLimit          = "rate_limit"
	PolicyTypeTokenLimit         = "token_limit"
	PolicyTypePromptFilter       = "prompt_filter"
	PolicyTypeAttribution        = "attribution"
	PolicyTypeManualReview       = "manual_review"
	PolicyTypeTransaction        = "transaction"
	PolicyTypeCustom             = "custom"
	PolicyTypeAllOf              = "all_of"
	PolicyTypeAnyOf              = "any_of"
	PolicyTypeNot                = "not"
	PolicyTypeBundleSubscription = "bundle_subscription"
)

// ValidPolicyTypes is the set of valid policy type strings.
var ValidPolicyTypes = map[string]bool{
	PolicyTypeAccessGroup:        true,
	PolicyTypeRateLimit:          true,
	PolicyTypeTokenLimit:         true,
	PolicyTypePromptFilter:       true,
	PolicyTypeAttribution:        true,
	PolicyTypeManualReview:       true,
	PolicyTypeTransaction:        true,
	PolicyTypeCustom:             true,
	PolicyTypeAllOf:              true,
	PolicyTypeAnyOf:              true,
	PolicyTypeNot:                true,
	PolicyTypeBundleSubscription: true,
}
