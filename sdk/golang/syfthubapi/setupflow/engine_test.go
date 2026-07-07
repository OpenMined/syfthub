package setupflow_test

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow/handlers"
)

// MockSetupIO implements setupflow.SetupIO for testing.
type MockSetupIO struct {
	PromptResponses  []string
	SelectResponses  []string
	ConfirmResponses []bool
	StatusMessages   []string
	ErrorMessages    []string
	promptIndex      int
	selectIndex      int
	confirmIndex     int
}

func (m *MockSetupIO) Prompt(msg string, opts setupflow.PromptOpts) (string, error) {
	if m.promptIndex >= len(m.PromptResponses) {
		return "", fmt.Errorf("no more prompt responses configured")
	}
	val := m.PromptResponses[m.promptIndex]
	m.promptIndex++
	return val, nil
}

func (m *MockSetupIO) Select(msg string, options []setupflow.SelectOption) (string, error) {
	if m.selectIndex >= len(m.SelectResponses) {
		return "", fmt.Errorf("no more select responses configured")
	}
	val := m.SelectResponses[m.selectIndex]
	m.selectIndex++
	return val, nil
}

func (m *MockSetupIO) Confirm(msg string) (bool, error) {
	if m.confirmIndex >= len(m.ConfirmResponses) {
		return false, fmt.Errorf("no more confirm responses configured")
	}
	val := m.ConfirmResponses[m.confirmIndex]
	m.confirmIndex++
	return val, nil
}

func (m *MockSetupIO) OpenBrowser(url string) error { return nil }
func (m *MockSetupIO) Status(msg string)            { m.StatusMessages = append(m.StatusMessages, msg) }
func (m *MockSetupIO) Error(msg string)             { m.ErrorMessages = append(m.ErrorMessages, msg) }

func newTestEngine() *setupflow.Engine {
	e := setupflow.NewEngine(
		setupflow.WithHandler("prompt", &handlers.PromptHandler{}),
		setupflow.WithHandler("select", &handlers.SelectHandler{}),
	)
	return e
}

func TestEngine_ExecutePrompt(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{PromptResponses: []string{"myvalue"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "key", Name: "API Key", Type: "prompt", Required: true,
					EnvKey: "API_KEY",
					Prompt: &nodeops.PromptConfig{Message: "Enter key:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Verify .env was written
	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	found := false
	for _, v := range envVars {
		if v.Key == "API_KEY" && v.Value == "myvalue" {
			found = true
		}
	}
	if !found {
		t.Error("expected API_KEY=myvalue in .env")
	}
}

func TestEngine_ExecuteSelect(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{SelectResponses: []string{"us-east-1"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "region", Name: "Region", Type: "select", Required: true,
					EnvKey: "REGION",
					Select: &nodeops.SelectConfig{
						Message: "Choose region:",
						Options: []nodeops.SelectOption{
							{Value: "us-east-1", Label: "US East"},
							{Value: "eu-west-1", Label: "EU West"},
						},
					},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	found := false
	for _, v := range envVars {
		if v.Key == "REGION" && v.Value == "us-east-1" {
			found = true
		}
	}
	if !found {
		t.Error("expected REGION=us-east-1 in .env")
	}
}

func TestEngine_ExecuteMultipleSteps(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{
		PromptResponses: []string{"my-key"},
		SelectResponses: []string{"us-east-1"},
	}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "key", Name: "Key", Type: "prompt", Required: true,
					EnvKey: "API_KEY",
					Prompt: &nodeops.PromptConfig{Message: "Enter key:"},
				},
				{
					ID: "region", Name: "Region", Type: "select", Required: true,
					EnvKey:    "REGION",
					DependsOn: []string{"key"},
					Select: &nodeops.SelectConfig{
						Options: []nodeops.SelectOption{
							{Value: "us-east-1", Label: "US East"},
						},
					},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	envMap := make(map[string]string)
	for _, v := range envVars {
		envMap[v.Key] = v.Value
	}
	if envMap["API_KEY"] != "my-key" {
		t.Error("expected API_KEY=my-key")
	}
	if envMap["REGION"] != "us-east-1" {
		t.Error("expected REGION=us-east-1")
	}
}

func TestEngine_SkipCompleted(t *testing.T) {
	dir := t.TempDir()

	// Write initial .env with the value
	nodeops.WriteEnvFile(filepath.Join(dir, ".env"), []nodeops.EnvVar{
		{Key: "API_KEY", Value: "existing"},
	})

	io := &MockSetupIO{} // No responses needed since step should be skipped
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State: &nodeops.SetupState{
			Version: "1",
			Steps: map[string]nodeops.StepState{
				"key": {Status: nodeops.StepStatusCompleted, CompletedAt: "2026-01-01T00:00:00Z"},
			},
		},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "key", Name: "Key", Type: "prompt", Required: true,
					EnvKey: "API_KEY",
					Prompt: &nodeops.PromptConfig{Message: "Enter key:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Verify the step was skipped (status message should say "already completed")
	found := false
	for _, msg := range io.StatusMessages {
		if msg == "Step 'Key' already completed, skipping" {
			found = true
		}
	}
	if !found {
		t.Errorf("expected skip message, got: %v", io.StatusMessages)
	}
}

func TestEngine_ForceRerun(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{PromptResponses: []string{"new-value"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		Force:       true,
		State: &nodeops.SetupState{
			Version: "1",
			Steps: map[string]nodeops.StepState{
				"key": {Status: nodeops.StepStatusCompleted, CompletedAt: "2026-01-01T00:00:00Z"},
			},
		},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "key", Name: "Key", Type: "prompt", Required: true,
					EnvKey: "API_KEY",
					Prompt: &nodeops.PromptConfig{Message: "Enter key:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	found := false
	for _, v := range envVars {
		if v.Key == "API_KEY" && v.Value == "new-value" {
			found = true
		}
	}
	if !found {
		t.Error("expected API_KEY=new-value in .env after force rerun")
	}
}

func TestEngine_OnlySteps(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{PromptResponses: []string{"value2"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		OnlySteps:   []string{"step2"},
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "step1", Name: "Step 1", Type: "prompt", Required: true,
					EnvKey: "KEY1",
					Prompt: &nodeops.PromptConfig{Message: "Enter 1:"},
				},
				{
					ID: "step2", Name: "Step 2", Type: "prompt", Required: true,
					EnvKey: "KEY2",
					Prompt: &nodeops.PromptConfig{Message: "Enter 2:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	envMap := make(map[string]string)
	for _, v := range envVars {
		envMap[v.Key] = v.Value
	}
	if _, ok := envMap["KEY1"]; ok {
		t.Error("step1 should have been skipped")
	}
	if envMap["KEY2"] != "value2" {
		t.Error("expected KEY2=value2")
	}
}

func TestEngine_RequiredStepFails(t *testing.T) {
	dir := t.TempDir()

	// No prompt responses configured — will cause error
	io := &MockSetupIO{}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "key", Name: "Key", Type: "prompt", Required: true,
					Prompt: &nodeops.PromptConfig{Message: "Enter key:"},
				},
			},
		},
	}

	engine := newTestEngine()
	err := engine.Execute(ctx)
	if err == nil {
		t.Fatal("expected error for failed required step")
	}
}

func TestEngine_OptionalStepFails(t *testing.T) {
	dir := t.TempDir()

	// No prompt responses — will cause error, but step is optional
	io := &MockSetupIO{}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "opt", Name: "Optional", Type: "prompt", Required: false,
					Prompt: &nodeops.PromptConfig{Message: "Enter optional:"},
				},
			},
		},
	}

	engine := newTestEngine()
	err := engine.Execute(ctx)
	if err != nil {
		t.Fatalf("expected no error for failed optional step, got: %v", err)
	}
}

func TestEngine_DependencyOrder(t *testing.T) {
	dir := t.TempDir()

	var executionOrder []string
	io := &MockSetupIO{
		PromptResponses: []string{"val_a", "val_b", "val_c"},
	}

	// Override StatusMessages to track execution order
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "c", Name: "C", Type: "prompt", Required: true,
					DependsOn: []string{"b"},
					Prompt:    &nodeops.PromptConfig{Message: "C:"},
				},
				{
					ID: "a", Name: "A", Type: "prompt", Required: true,
					Prompt: &nodeops.PromptConfig{Message: "A:"},
				},
				{
					ID: "b", Name: "B", Type: "prompt", Required: true,
					DependsOn: []string{"a"},
					Prompt:    &nodeops.PromptConfig{Message: "B:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Check execution order from status messages
	for _, msg := range io.StatusMessages {
		if msg == "Running: A" {
			executionOrder = append(executionOrder, "a")
		} else if msg == "Running: B" {
			executionOrder = append(executionOrder, "b")
		} else if msg == "Running: C" {
			executionOrder = append(executionOrder, "c")
		}
	}

	if len(executionOrder) != 3 {
		t.Fatalf("expected 3 executions, got %d", len(executionOrder))
	}

	// a must be before b, b must be before c
	aIdx, bIdx, cIdx := -1, -1, -1
	for i, id := range executionOrder {
		switch id {
		case "a":
			aIdx = i
		case "b":
			bIdx = i
		case "c":
			cIdx = i
		}
	}
	if aIdx > bIdx || bIdx > cIdx {
		t.Errorf("incorrect execution order: %v", executionOrder)
	}
}

func TestEngine_TemplateResolution(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{
		PromptResponses: []string{"initial", "resolved"},
	}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "a", Name: "A", Type: "prompt", Required: true,
					EnvKey: "KEY_A",
					Prompt: &nodeops.PromptConfig{Message: "Enter A:"},
				},
				{
					ID: "b", Name: "B", Type: "prompt", Required: true,
					DependsOn: []string{"a"},
					EnvKey:    "KEY_B",
					Prompt:    &nodeops.PromptConfig{Message: "A was: {{steps.a.value}}. Enter B:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Both values should be in .env
	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	envMap := make(map[string]string)
	for _, v := range envVars {
		envMap[v.Key] = v.Value
	}
	if envMap["KEY_A"] != "initial" {
		t.Error("expected KEY_A=initial")
	}
	if envMap["KEY_B"] != "resolved" {
		t.Error("expected KEY_B=resolved")
	}
}

func TestEngine_OutputsWrittenToEnv(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{PromptResponses: []string{"my-token"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "token", Name: "Token", Type: "prompt", Required: true,
					Outputs: map[string]string{
						"AUTH_TOKEN": "{{steps.token.value}}",
					},
					Prompt: &nodeops.PromptConfig{Message: "Enter token:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	envMap := make(map[string]string)
	for _, v := range envVars {
		envMap[v.Key] = v.Value
	}
	if envMap["AUTH_TOKEN"] != "my-token" {
		t.Errorf("expected AUTH_TOKEN=my-token, got '%s'", envMap["AUTH_TOKEN"])
	}
}

func TestEngine_StateUpdated(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{PromptResponses: []string{"val"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "s1", Name: "S1", Type: "prompt", Required: true,
					Prompt: &nodeops.PromptConfig{Message: "Enter:"},
				},
			},
		},
	}

	engine := newTestEngine()
	engine.Execute(ctx)

	// Read state from disk
	state, _ := nodeops.ReadSetupState(dir)
	if ss, ok := state.Steps["s1"]; !ok {
		t.Error("expected step s1 in state")
	} else if ss.Status != nodeops.StepStatusCompleted {
		t.Errorf("expected completed, got %s", ss.Status)
	}
}

func TestEngine_ResumeAfterFailure(t *testing.T) {
	dir := t.TempDir()

	// First run: step1 completed, step2 failed
	nodeops.WriteSetupState(dir, &nodeops.SetupState{
		Version: "1",
		Steps: map[string]nodeops.StepState{
			"s1": {Status: nodeops.StepStatusCompleted, CompletedAt: "2026-01-01T00:00:00Z"},
			"s2": {Status: nodeops.StepStatusFailed, Error: "previous failure"},
		},
	})
	nodeops.WriteEnvFile(filepath.Join(dir, ".env"), []nodeops.EnvVar{
		{Key: "KEY1", Value: "val1"},
	})

	// Second run: step2 should be retried
	io := &MockSetupIO{PromptResponses: []string{"val2"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State: &nodeops.SetupState{
			Version: "1",
			Steps: map[string]nodeops.StepState{
				"s1": {Status: nodeops.StepStatusCompleted, CompletedAt: "2026-01-01T00:00:00Z"},
				"s2": {Status: nodeops.StepStatusFailed, Error: "previous failure"},
			},
		},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{
					ID: "s1", Name: "Step 1", Type: "prompt", Required: true,
					EnvKey: "KEY1",
					Prompt: &nodeops.PromptConfig{Message: "Enter 1:"},
				},
				{
					ID: "s2", Name: "Step 2", Type: "prompt", Required: true,
					EnvKey:    "KEY2",
					DependsOn: []string{"s1"},
					Prompt:    &nodeops.PromptConfig{Message: "Enter 2:"},
				},
			},
		},
	}

	engine := newTestEngine()
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	envMap := make(map[string]string)
	for _, v := range envVars {
		envMap[v.Key] = v.Value
	}
	if envMap["KEY2"] != "val2" {
		t.Error("expected KEY2=val2 after resume")
	}
}

func TestEngine_CustomHandler(t *testing.T) {
	dir := t.TempDir()

	// Create a custom handler that overrides the built-in prompt handler
	customHandler := &mockStepHandler{
		executeFunc: func(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
			return &setupflow.StepResult{Value: "custom-result"}, nil
		},
	}

	engine := setupflow.NewEngine(
		setupflow.WithHandler("prompt", customHandler),
		setupflow.WithHandler("select", &handlers.SelectHandler{}),
	)

	io := &MockSetupIO{}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{ID: "s1", Name: "Custom Step", Type: "prompt", Required: true,
					EnvKey: "CUSTOM_KEY",
					Prompt: &nodeops.PromptConfig{Message: "Enter:"}},
			},
		},
	}

	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	found := false
	for _, v := range envVars {
		if v.Key == "CUSTOM_KEY" && v.Value == "custom-result" {
			found = true
		}
	}
	if !found {
		t.Error("expected CUSTOM_KEY=custom-result")
	}
}

func TestEngine_UnknownType(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{ID: "s1", Name: "Unknown", Type: "prompt", Required: true,
					Prompt: &nodeops.PromptConfig{Message: "m"}},
			},
		},
	}

	// Engine without any handlers registered
	engine := setupflow.NewEngine()
	err := engine.Execute(ctx)
	if err == nil {
		t.Fatal("expected error for unregistered type")
	}
}

// mockStepHandler is a test helper for custom step types.
type mockStepHandler struct {
	executeFunc  func(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error)
	validateFunc func(step *nodeops.SetupStep) error
}

func (h *mockStepHandler) Execute(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
	if h.executeFunc != nil {
		return h.executeFunc(step, ctx)
	}
	return &setupflow.StepResult{}, nil
}

func (h *mockStepHandler) Validate(step *nodeops.SetupStep) error {
	if h.validateFunc != nil {
		return h.validateFunc(step)
	}
	return nil
}

// Ensure .setup-state.json is written with 0600 permissions
func TestEngine_StateFilePermissions(t *testing.T) {
	dir := t.TempDir()

	io := &MockSetupIO{PromptResponses: []string{"val"}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          io,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       &nodeops.SetupState{Version: "1", Steps: make(map[string]nodeops.StepState)},
		Spec: &nodeops.SetupSpec{
			Version: "1",
			Steps: []nodeops.SetupStep{
				{ID: "s1", Name: "S1", Type: "prompt", Required: true,
					Prompt: &nodeops.PromptConfig{Message: "m"}},
			},
		},
	}

	engine := newTestEngine()
	engine.Execute(ctx)

	info, err := os.Stat(filepath.Join(dir, ".setup-state.json"))
	if err != nil {
		t.Fatalf("stat error: %v", err)
	}
	perm := info.Mode().Perm()
	if perm != 0600 {
		t.Errorf("expected permissions 0600, got %o", perm)
	}
}
