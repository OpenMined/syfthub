package setupflow

import "github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"

// StepHandler executes a single step type.
// Implementations are stateless — all state flows through SetupContext.
type StepHandler interface {
	// Execute runs the step and returns its result.
	Execute(step *nodeops.SetupStep, ctx *SetupContext) (*StepResult, error)

	// Validate checks the step configuration before execution.
	// Called during engine initialization, not at execution time.
	Validate(step *nodeops.SetupStep) error
}
