package setupflow

import "encoding/json"

// StepResult holds the outputs of a completed step.
type StepResult struct {
	// Value is the primary output (for prompt: user input; for select: chosen value).
	Value string

	// Outputs is a map of env var name -> resolved value.
	// Populated by the engine from the step's outputs map after template resolution.
	Outputs map[string]string

	// Response is the raw JSON response body (for http and oauth2 steps).
	// Used by templates: {{steps.X.response.path.to.field}}
	Response json.RawMessage

	// Metadata holds handler-specific metadata (e.g., expires_in for oauth tokens).
	Metadata map[string]string
}
