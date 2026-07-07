package handlers

import (
	"fmt"
	"regexp"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// PromptHandler handles type=prompt steps.
type PromptHandler struct{}

func (h *PromptHandler) Validate(step *nodeops.SetupStep) error {
	if step.Prompt == nil {
		return fmt.Errorf("prompt config is required for type 'prompt'")
	}
	if step.Prompt.Message == "" {
		return fmt.Errorf("prompt.message is required")
	}
	if step.Prompt.Validate != nil && step.Prompt.Validate.Pattern != "" {
		if _, err := regexp.Compile(step.Prompt.Validate.Pattern); err != nil {
			return fmt.Errorf("invalid validate.pattern: %w", err)
		}
	}
	return nil
}

func (h *PromptHandler) Execute(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
	cfg := step.Prompt

	// Compile the validation regex once before the retry loop.
	var validationRegex *regexp.Regexp
	if cfg.Validate != nil && cfg.Validate.Pattern != "" {
		validationRegex = regexp.MustCompile(cfg.Validate.Pattern)
	}

	for {
		value, err := ctx.IO.Prompt(cfg.Message, setupflow.PromptOpts{
			Secret:  cfg.Secret,
			Default: cfg.Default,
		})
		if err != nil {
			return nil, err
		}

		// Apply default
		if value == "" && cfg.Default != "" {
			value = cfg.Default
		}

		// Validate required
		if value == "" && step.Required {
			ctx.IO.Error("This field is required.")
			continue
		}

		// Validate pattern
		if validationRegex != nil && value != "" {
			if !validationRegex.MatchString(value) {
				msg := cfg.Validate.Message
				if msg == "" {
					msg = fmt.Sprintf("Value must match pattern: %s", cfg.Validate.Pattern)
				}
				ctx.IO.Error(msg)
				continue
			}
		}

		return &setupflow.StepResult{Value: value}, nil
	}
}
