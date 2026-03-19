package main

import (
	"context"
	"fmt"
	"path/filepath"
	"sync"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow/handlers"
)

// setupState tracks the currently running setup flow.
// A flow is considered running when io != nil.
type setupState struct {
	mu     sync.Mutex
	io     *WailsSetupIO
	cancel context.CancelFunc
	slug   string
}

// RunEndpointSetup starts the setup flow for an endpoint asynchronously.
// Progress and prompts are delivered via Wails events on the "setupflow:*" channels.
// Emits "setupflow:complete" on success or "setupflow:failed" on error.
func (a *App) RunEndpointSetup(slug string, force bool) error {
	a.mu.RLock()
	config := a.config
	settings := a.settings
	a.mu.RUnlock()

	if config == nil {
		return fmt.Errorf("app not configured")
	}

	endpointDir := filepath.Join(config.EndpointsPath, slug)

	// Parse setup.yaml
	setupPath := filepath.Join(endpointDir, "setup.yaml")
	spec, err := nodeops.ParseSetupYaml(setupPath)
	if err != nil {
		return fmt.Errorf("failed to parse setup.yaml: %w", err)
	}
	if spec == nil {
		return fmt.Errorf("no setup.yaml found for endpoint '%s'", slug)
	}

	// Load existing state
	state, _ := nodeops.ReadSetupState(endpointDir)
	if state == nil {
		state = &nodeops.SetupState{Version: "1", Steps: map[string]nodeops.StepState{}}
	}

	// Cancel any existing setup
	a.cancelRunningSetup()

	// Create cancellation context
	cancelCtx, cancel := context.WithCancel(context.Background())

	// Create WailsSetupIO
	sio := NewWailsSetupIO(a.ctx, cancelCtx)

	// Store setup state
	a.setup.mu.Lock()
	a.setup.io = sio
	a.setup.cancel = cancel
	a.setup.slug = slug
	a.setup.mu.Unlock()

	// Resolve API key and hub URL from settings
	apiKey := ""
	hubURL := ""
	username := ""
	if settings != nil {
		apiKey = settings.APIKey
		hubURL = settings.SyftHubURL
	}
	a.mu.RLock()
	username = a.username
	a.mu.RUnlock()

	// Mark this endpoint as setting up
	a.setRuntimeState(slug, RuntimeStateSettingUp)

	// Notify frontend that setup is starting (carries the slug for the dialog title)
	runtime.EventsEmit(a.ctx, "setupflow:started", slug)
	a.notifyEndpointsChanged()

	// Run setup in background goroutine
	go func() {
		defer func() {
			a.setup.mu.Lock()
			// Only clear state if this goroutine still owns it.
			// cancelRunningSetup may have started a new flow; in that case the
			// new flow has already overwritten a.setup.io, and we must not clobber it.
			if a.setup.io == sio {
				a.setup.io = nil
				a.setup.cancel = nil
				a.setup.slug = ""
			}
			a.setup.mu.Unlock()
		}()

		engine := handlers.NewDefaultEngine()
		sctx := &setupflow.SetupContext{
			EndpointDir: endpointDir,
			Slug:        slug,
			HubURL:      hubURL,
			Username:    username,
			APIKey:      apiKey,
			IO:          sio,
			StepOutputs: make(map[string]*setupflow.StepResult),
			State:       state,
			Spec:        spec,
			Force:       force,
		}

		runtime.LogInfo(a.ctx, fmt.Sprintf("Setup engine starting for '%s' (%d steps)", slug, len(spec.Steps)))

		if err := engine.Execute(sctx); err != nil {
			runtime.LogError(a.ctx, fmt.Sprintf("Setup engine failed for '%s': %v", slug, err))
			a.clearRuntimeState(slug)
			// Only emit error if not cancelled
			if cancelCtx.Err() == nil {
				runtime.EventsEmit(a.ctx, "setupflow:failed", err.Error())
			}
			a.notifyEndpointsChanged()
			return
		}

		// Transition to initializing — reload the endpoint so it picks up
		// new .env values, dependencies, etc.
		a.setRuntimeState(slug, RuntimeStateInitializing)
		runtime.EventsEmit(a.ctx, "setupflow:status", "Loading endpoint...")

		if a.core != nil {
			if err := a.core.ReloadEndpoints(); err != nil {
				runtime.LogWarning(a.ctx, fmt.Sprintf("Failed to reload endpoints after setup: %v", err))
			}
		}

		// Get final status — spec is already in memory; re-read state only.
		finalState, _ := nodeops.ReadSetupState(endpointDir)
		statusInfo := toSetupStatusInfo(nodeops.ComputeSetupStatus(spec, finalState))

		// Clear runtime state — endpoint is now in its steady state
		a.clearRuntimeState(slug)

		runtime.EventsEmit(a.ctx, "setupflow:complete", statusInfo)
		a.notifyEndpointsChanged()
	}()

	return nil
}

// GetSetupStatus returns the setup status for an endpoint.
func (a *App) GetSetupStatus(slug string) (*SetupStatusInfo, error) {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return nil, fmt.Errorf("app not configured")
	}

	endpointDir := filepath.Join(config.EndpointsPath, slug)
	status, err := nodeops.GetSetupStatus(endpointDir)
	if err != nil {
		return nil, err
	}

	return toSetupStatusInfo(status), nil
}

// GetSetupSpec returns the parsed setup spec with current step statuses.
func (a *App) GetSetupSpec(slug string) (*SetupSpecInfo, error) {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()

	if config == nil {
		return nil, fmt.Errorf("app not configured")
	}

	endpointDir := filepath.Join(config.EndpointsPath, slug)
	setupPath := filepath.Join(endpointDir, "setup.yaml")
	spec, err := nodeops.ParseSetupYaml(setupPath)
	if err != nil {
		return nil, err
	}
	if spec == nil {
		return nil, fmt.Errorf("no setup.yaml found for endpoint '%s'", slug)
	}

	state, _ := nodeops.ReadSetupState(endpointDir)
	return toSetupSpecInfoFromState(spec, state), nil
}

// getSetupIO returns the active WailsSetupIO, or an error if no setup is running.
func (a *App) getSetupIO() (*WailsSetupIO, error) {
	a.setup.mu.Lock()
	sio := a.setup.io
	a.setup.mu.Unlock()
	if sio == nil {
		return nil, fmt.Errorf("no setup flow running")
	}
	return sio, nil
}

// RespondToSetupPrompt sends a user's prompt response to the running setup flow.
func (a *App) RespondToSetupPrompt(value string) error {
	sio, err := a.getSetupIO()
	if err != nil {
		return err
	}
	select {
	case sio.promptCh <- value:
		return nil
	case <-sio.cancelCtx.Done():
		return fmt.Errorf("setup was cancelled")
	}
}

// RespondToSetupSelect sends a user's select response to the running setup flow.
func (a *App) RespondToSetupSelect(value string) error {
	sio, err := a.getSetupIO()
	if err != nil {
		return err
	}
	select {
	case sio.selectCh <- value:
		return nil
	case <-sio.cancelCtx.Done():
		return fmt.Errorf("setup was cancelled")
	}
}

// RespondToSetupConfirm sends a user's confirm response to the running setup flow.
func (a *App) RespondToSetupConfirm(confirmed bool) error {
	sio, err := a.getSetupIO()
	if err != nil {
		return err
	}
	select {
	case sio.confirmCh <- confirmed:
		return nil
	case <-sio.cancelCtx.Done():
		return fmt.Errorf("setup was cancelled")
	}
}

// CancelSetup cancels the currently running setup flow.
func (a *App) CancelSetup() error {
	a.setup.mu.Lock()
	cancel := a.setup.cancel
	slug := a.setup.slug
	a.setup.mu.Unlock()

	if cancel == nil {
		return fmt.Errorf("no setup flow running")
	}

	cancel()
	if slug != "" {
		a.clearRuntimeState(slug)
		a.notifyEndpointsChanged()
	}
	return nil
}

// cancelRunningSetup cancels any running setup flow without returning an error.
func (a *App) cancelRunningSetup() {
	a.setup.mu.Lock()
	slug := a.setup.slug
	if a.setup.cancel != nil {
		a.setup.cancel()
	}
	a.setup.mu.Unlock()
	if slug != "" {
		a.clearRuntimeState(slug)
	}
}

// --- Converter helpers ---

func toSetupStatusInfo(s *nodeops.SetupStatus) *SetupStatusInfo {
	if s == nil {
		return nil
	}
	return &SetupStatusInfo{
		IsComplete:   s.IsComplete,
		TotalSteps:   s.TotalSteps,
		CompletedN:   s.CompletedN,
		PendingSteps: s.PendingSteps,
		ExpiredSteps: s.ExpiredSteps,
	}
}

func toSetupSpecInfoFromState(spec *nodeops.SetupSpec, state *nodeops.SetupState) *SetupSpecInfo {
	if spec == nil {
		return nil
	}

	steps := make([]SetupStepInfo, len(spec.Steps))
	for i, step := range spec.Steps {
		status := nodeops.StepStatusPending
		expiresAt := ""
		if state != nil {
			if ss, ok := state.Steps[step.ID]; ok {
				status = ss.Status
				expiresAt = ss.ExpiresAt
			}
		}
		steps[i] = SetupStepInfo{
			ID:          step.ID,
			Name:        step.Name,
			Description: step.Description,
			Type:        step.Type,
			Required:    step.Required,
			Status:      status,
			ExpiresAt:   expiresAt,
		}
	}

	return &SetupSpecInfo{
		Version: spec.Version,
		Steps:   steps,
	}
}
