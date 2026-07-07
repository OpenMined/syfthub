package setupflow

import "github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"

// SetupContext holds all state during setup execution.
type SetupContext struct {
	// EndpointDir is the absolute path to the endpoint directory.
	EndpointDir string

	// Slug is the endpoint slug.
	Slug string

	// HubURL is the SyftHub hub URL (e.g., "https://syfthub-dev.openmined.org").
	HubURL string

	// Username is the authenticated user's username.
	Username string

	// APIKey is the user's API key / PAT (for hub-managed OAuth).
	APIKey string

	// IO is the user interaction interface.
	IO SetupIO

	// StepOutputs holds results from completed steps, keyed by step ID.
	StepOutputs map[string]*StepResult

	// State is the current setup state (loaded from .setup-state.json).
	State *nodeops.SetupState

	// Spec is the parsed setup.yaml.
	Spec *nodeops.SetupSpec

	// Force re-runs already-completed steps if true.
	Force bool

	// OnlySteps, if non-empty, limits execution to these step IDs.
	OnlySteps []string
}
