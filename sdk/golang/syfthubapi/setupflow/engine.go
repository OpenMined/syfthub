package setupflow

import (
	"fmt"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// Engine orchestrates the execution of setup steps.
type Engine struct {
	handlers map[string]StepHandler
}

// EngineOption configures the engine.
type EngineOption func(*Engine)

// WithHandler registers a custom step handler, overriding any built-in
// handler for that type. This is the extensibility valve for novel step types.
func WithHandler(stepType string, handler StepHandler) EngineOption {
	return func(e *Engine) {
		e.handlers[stepType] = handler
	}
}

// NewEngine creates an engine with all built-in handlers registered.
func NewEngine(opts ...EngineOption) *Engine {
	e := &Engine{
		handlers: make(map[string]StepHandler),
	}

	// Built-in handlers are registered by the init functions in the handlers package.
	// They are registered here to avoid import cycles.
	// Phase 1: prompt and select are registered by RegisterBuiltinHandlers.
	// Phase 2: oauth2, http, template are added.

	for _, opt := range opts {
		opt(e)
	}
	return e
}

// RegisterHandler registers a step handler for a given type.
func (e *Engine) RegisterHandler(stepType string, handler StepHandler) {
	e.handlers[stepType] = handler
}

// Execute runs all steps in dependency order.
func (e *Engine) Execute(ctx *SetupContext) error {
	// 1. Structural validation
	if err := nodeops.ValidateSetupSpec(ctx.Spec); err != nil {
		return err
	}

	// 2. Handler validation
	if err := e.ValidateSpec(ctx.Spec); err != nil {
		return err
	}

	// 3. Topological sort
	order, err := nodeops.TopologicalSort(ctx.Spec.Steps)
	if err != nil {
		return err
	}

	// 4. Build step lookup
	stepMap := make(map[string]*nodeops.SetupStep)
	for i := range ctx.Spec.Steps {
		stepMap[ctx.Spec.Steps[i].ID] = &ctx.Spec.Steps[i]
	}

	// 5. Execute in order
	var envCache map[string]string // lazily loaded for skipped-step output recovery
	anyExecuted := false
	for _, stepID := range order {
		step := stepMap[stepID]

		// Skip filter
		if len(ctx.OnlySteps) > 0 && !slices.Contains(ctx.OnlySteps, stepID) {
			continue
		}

		// Already completed?
		if !ctx.Force {
			if ss, ok := ctx.State.Steps[stepID]; ok && ss.Status == nodeops.StepStatusCompleted {
				// Check expiry
				if ss.ExpiresAt == "" || !isExpired(ss.ExpiresAt) {
					ctx.IO.Status(fmt.Sprintf("Step '%s' already completed, skipping", step.Name))
					// Populate StepOutputs from .env so downstream templates resolve
					if envCache == nil {
						envCache = loadEnvCache(ctx.EndpointDir)
					}
					e.loadStepOutputsFromEnv(stepID, step, ctx, envCache)
					continue
				}
				ctx.IO.Status(fmt.Sprintf("Step '%s' expired, re-running", step.Name))
			}
		}

		// Resolve templates
		resolved, err := ResolveStep(step, ctx)
		if err != nil {
			if !step.Required {
				ctx.IO.Error(fmt.Sprintf("Skipping optional step '%s': %v", step.Name, err))
				continue
			}
			return fmt.Errorf("step '%s': template resolution failed: %w", stepID, err)
		}

		// Execute
		handler, ok := e.handlers[step.Type]
		if !ok {
			return fmt.Errorf("step '%s': unknown type '%s'", stepID, step.Type)
		}

		anyExecuted = true
		ctx.IO.Status(fmt.Sprintf("Running: %s", step.Name))
		result, err := handler.Execute(resolved, ctx)
		if err != nil {
			// Update state as failed
			ctx.State.Steps[stepID] = nodeops.StepState{
				Status: nodeops.StepStatusFailed,
				Error:  err.Error(),
			}
			nodeops.WriteSetupState(ctx.EndpointDir, ctx.State)

			if !step.Required {
				ctx.IO.Error(fmt.Sprintf("Optional step '%s' failed: %v", step.Name, err))
				continue
			}
			return fmt.Errorf("step '%s' failed: %w", stepID, err)
		}

		// Store result
		ctx.StepOutputs[stepID] = result

		// Resolve outputs templates and merge to .env
		envUpdates := make(map[string]string)
		if step.EnvKey != "" && result.Value != "" {
			envUpdates[step.EnvKey] = result.Value
		}
		for envKey, tmpl := range step.Outputs {
			val, err := ResolveTemplate(tmpl, ctx)
			if err != nil {
				// For outputs, reference the step's own result
				// (e.g., {{response.access_token}} is shorthand for current step)
				val, err = resolveStepLocalTemplate(tmpl, result)
				if err != nil {
					return fmt.Errorf("step '%s': output '%s' resolution failed: %w", stepID, envKey, err)
				}
			}
			envUpdates[envKey] = val
		}
		// Also store resolved outputs in the result for downstream template access
		if result.Outputs == nil {
			result.Outputs = make(map[string]string)
		}
		maps.Copy(result.Outputs, envUpdates)

		// Write to .env
		if len(envUpdates) > 0 {
			if err := mergeEnvFile(ctx.EndpointDir, envUpdates); err != nil {
				return fmt.Errorf("step '%s': failed to write .env: %w", stepID, err)
			}
		}

		// Update state
		stepState := nodeops.StepState{
			Status:      nodeops.StepStatusCompleted,
			CompletedAt: time.Now().UTC().Format(time.RFC3339),
		}
		if expiresIn, ok := result.Metadata["expires_in"]; ok {
			stepState.ExpiresAt = computeExpiry(expiresIn)
		}
		ctx.State.Steps[stepID] = stepState
		nodeops.WriteSetupState(ctx.EndpointDir, ctx.State)
	}

	// Touch .env to ensure the file watcher triggers a reload after setup completes.
	// This is necessary because .setup-state.json writes don't trigger watcher events
	// (dotfiles other than .env are ignored to avoid reload cascades during setup).
	// Skip when no steps actually executed (e.g. all already completed) to avoid
	// spurious watcher reloads.
	if anyExecuted {
		envPath := filepath.Join(ctx.EndpointDir, ".env")
		now := time.Now()
		if err := os.Chtimes(envPath, now, now); err != nil {
			if os.IsNotExist(err) {
				// .env may not exist for exec-only setups; create an empty one
				os.WriteFile(envPath, nil, 0600)
			}
			// Other errors (permission denied, etc.) are non-fatal for this touch operation
		}
	}

	return nil
}

// ValidateSpec validates all steps against their registered handlers.
func (e *Engine) ValidateSpec(spec *nodeops.SetupSpec) error {
	for _, step := range spec.Steps {
		handler, ok := e.handlers[step.Type]
		if !ok {
			return fmt.Errorf("step '%s': no handler registered for type '%s'", step.ID, step.Type)
		}
		if err := handler.Validate(&step); err != nil {
			return fmt.Errorf("step '%s': validation failed: %w", step.ID, err)
		}
	}
	return nil
}

// loadEnvCache reads the .env file once and returns a key→value map.
func loadEnvCache(endpointDir string) map[string]string {
	envVars, err := nodeops.ReadEnvFile(endpointDir + "/.env")
	if err != nil {
		return nil
	}
	m := make(map[string]string, len(envVars))
	for _, v := range envVars {
		m[v.Key] = v.Value
	}
	return m
}

// loadStepOutputsFromEnv populates step outputs from a cached env map for skipped steps.
func (e *Engine) loadStepOutputsFromEnv(stepID string, step *nodeops.SetupStep, ctx *SetupContext, envMap map[string]string) {
	result := &StepResult{
		Outputs: make(map[string]string),
	}

	// Populate from env_key
	if step.EnvKey != "" {
		if val, ok := envMap[step.EnvKey]; ok {
			result.Value = val
			result.Outputs[step.EnvKey] = val
		}
	}

	// Populate from outputs
	for envKey := range step.Outputs {
		if val, ok := envMap[envKey]; ok {
			result.Outputs[envKey] = val
		}
	}

	ctx.StepOutputs[stepID] = result
}

// isExpired checks if an RFC3339 timestamp is in the past.
func isExpired(rfc3339 string) bool {
	t, err := time.Parse(time.RFC3339, rfc3339)
	if err != nil {
		return false
	}
	return time.Now().After(t)
}

// computeExpiry computes an absolute expiry time from an expires_in value (seconds).
func computeExpiry(expiresIn string) string {
	seconds, err := strconv.ParseInt(expiresIn, 10, 64)
	if err != nil {
		return ""
	}
	return time.Now().UTC().Add(time.Duration(seconds) * time.Second).Format(time.RFC3339)
}
