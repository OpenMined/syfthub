package handlers

import (
	"fmt"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// TemplateHandler handles type=template steps.
// Computes a derived value from templates — no user interaction.
type TemplateHandler struct{}

func (h *TemplateHandler) Validate(step *nodeops.SetupStep) error {
	if step.Template == nil {
		return fmt.Errorf("template config is required for type 'template'")
	}
	if step.Template.Value == "" {
		return fmt.Errorf("template.value is required")
	}
	return nil
}

func (h *TemplateHandler) Execute(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
	// Template resolution already happened in engine's ResolveStep.
	// The resolved value is in step.Template.Value.
	return &setupflow.StepResult{Value: step.Template.Value}, nil
}
