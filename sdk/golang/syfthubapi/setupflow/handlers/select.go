package handlers

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// SelectHandler handles type=select steps.
type SelectHandler struct{}

func (h *SelectHandler) Validate(step *nodeops.SetupStep) error {
	if step.Select == nil {
		return fmt.Errorf("select config is required for type 'select'")
	}
	if len(step.Select.Options) == 0 && step.Select.OptionsFrom == nil {
		return fmt.Errorf("select requires options or options_from")
	}
	return nil
}

func (h *SelectHandler) Execute(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
	cfg := step.Select

	// Build options list
	var options []setupflow.SelectOption

	if len(cfg.Options) > 0 {
		// Static options
		for _, o := range cfg.Options {
			options = append(options, setupflow.SelectOption{
				Value: o.Value,
				Label: o.Label,
			})
		}
	} else if cfg.OptionsFrom != nil {
		// Dynamic options from a prior http step's response (Phase 2)
		opts, err := resolveDynamicOptions(cfg.OptionsFrom, ctx)
		if err != nil {
			return nil, fmt.Errorf("failed to resolve dynamic options: %w", err)
		}
		options = opts
	}

	if len(options) == 0 {
		return nil, fmt.Errorf("no options available")
	}

	// Present to user
	msg := cfg.Message
	if msg == "" {
		msg = step.Name
	}

	value, err := ctx.IO.Select(msg, options)
	if err != nil {
		return nil, err
	}

	return &setupflow.StepResult{Value: value}, nil
}

// resolveDynamicOptions resolves select options from a prior step's HTTP response.
func resolveDynamicOptions(cfg *nodeops.OptionsFromConfig, ctx *setupflow.SetupContext) ([]setupflow.SelectOption, error) {
	// Phase 2 implementation — for now return error if options_from is used without prior step
	stepResult, ok := ctx.StepOutputs[cfg.StepID]
	if !ok {
		return nil, fmt.Errorf("step '%s' has not completed yet", cfg.StepID)
	}

	if stepResult.Response == nil {
		return nil, fmt.Errorf("step '%s' has no response data", cfg.StepID)
	}

	return resolveDynamicOptionsFromResponse(stepResult.Response, cfg)
}

// resolveDynamicOptionsFromResponse extracts select options from a JSON response.
func resolveDynamicOptionsFromResponse(response json.RawMessage, cfg *nodeops.OptionsFromConfig) ([]setupflow.SelectOption, error) {
	// Parse the JSON response
	var data interface{}
	if err := json.Unmarshal(response, &data); err != nil {
		return nil, fmt.Errorf("failed to parse response JSON: %w", err)
	}

	// Navigate to the specified path
	current := data
	if cfg.Path != "" {
		parts := strings.Split(cfg.Path, ".")
		for _, part := range parts {
			m, ok := current.(map[string]interface{})
			if !ok {
				return nil, fmt.Errorf("cannot navigate path '%s': not an object", cfg.Path)
			}
			current, ok = m[part]
			if !ok {
				return nil, fmt.Errorf("path '%s': key '%s' not found", cfg.Path, part)
			}
		}
	}

	// Expect an array
	items, ok := current.([]interface{})
	if !ok {
		return nil, fmt.Errorf("options path does not resolve to an array")
	}

	// Map to SelectOption
	var options []setupflow.SelectOption
	for _, item := range items {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		value := fmt.Sprint(m[cfg.ValueField])
		label := fmt.Sprint(m[cfg.LabelField])
		if value != "" {
			options = append(options, setupflow.SelectOption{Value: value, Label: label})
		}
	}

	return options, nil
}
