package nodeops

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestParseSetupYaml_Valid(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "setup.yaml")
	content := `
version: "1"
steps:
  - id: api_key
    name: "API Key"
    type: prompt
    required: true
    env_key: API_KEY
    prompt:
      message: "Enter your API key:"
      secret: true
  - id: region
    name: "Region"
    type: select
    required: true
    env_key: REGION
    depends_on: [api_key]
    select:
      message: "Choose a region:"
      options:
        - value: us-east-1
          label: "US East"
        - value: eu-west-1
          label: "EU West"
  - id: auth
    name: "Auth"
    type: oauth2
    required: true
    oauth2:
      auth_url: "https://example.com/auth"
      token_url: "https://example.com/token"
      scopes: ["read", "write"]
  - id: verify
    name: "Verify"
    type: http
    required: false
    depends_on: [api_key]
    http:
      method: GET
      url: "https://api.example.com/verify"
  - id: webhook_url
    name: "Webhook URL"
    type: template
    required: true
    env_key: WEBHOOK_URL
    template:
      value: "https://example.com/webhook/{{steps.api_key.value}}"
`
	os.WriteFile(path, []byte(content), 0644)

	spec, err := ParseSetupYaml(path)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if spec == nil {
		t.Fatal("expected non-nil spec")
	}
	if spec.Version != "1" {
		t.Errorf("expected version '1', got '%s'", spec.Version)
	}
	if len(spec.Steps) != 5 {
		t.Fatalf("expected 5 steps, got %d", len(spec.Steps))
	}
	if spec.Steps[0].Prompt == nil {
		t.Error("expected prompt config for step 0")
	}
	if spec.Steps[0].Prompt.Secret != true {
		t.Error("expected secret=true for prompt step")
	}
	if spec.Steps[1].Select == nil {
		t.Error("expected select config for step 1")
	}
	if len(spec.Steps[1].Select.Options) != 2 {
		t.Errorf("expected 2 options, got %d", len(spec.Steps[1].Select.Options))
	}
	if spec.Steps[2].OAuth2 == nil {
		t.Error("expected oauth2 config for step 2")
	}
	if spec.Steps[3].HTTP == nil {
		t.Error("expected http config for step 3")
	}
	if spec.Steps[4].Template == nil {
		t.Error("expected template config for step 4")
	}
}

func TestParseSetupYaml_NotFound(t *testing.T) {
	spec, err := ParseSetupYaml("/nonexistent/path/setup.yaml")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if spec != nil {
		t.Error("expected nil spec for nonexistent file")
	}
}

func TestParseSetupYaml_InvalidYAML(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "setup.yaml")
	os.WriteFile(path, []byte("not: valid: yaml: ["), 0644)

	_, err := ParseSetupYaml(path)
	if err == nil {
		t.Fatal("expected error for invalid YAML")
	}
}

func TestWriteSetupYaml_RoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "setup.yaml")

	original := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{
				ID:       "api_key",
				Name:     "API Key",
				Type:     "prompt",
				Required: true,
				EnvKey:   "API_KEY",
				Prompt: &PromptConfig{
					Message: "Enter your API key:",
					Secret:  true,
				},
			},
		},
	}

	if err := WriteSetupYaml(path, original); err != nil {
		t.Fatalf("write error: %v", err)
	}

	parsed, err := ParseSetupYaml(path)
	if err != nil {
		t.Fatalf("parse error: %v", err)
	}

	if parsed.Version != original.Version {
		t.Errorf("version mismatch: %s vs %s", parsed.Version, original.Version)
	}
	if len(parsed.Steps) != 1 {
		t.Fatalf("expected 1 step, got %d", len(parsed.Steps))
	}
	if parsed.Steps[0].ID != "api_key" {
		t.Errorf("step ID mismatch")
	}
	if parsed.Steps[0].Prompt.Message != "Enter your API key:" {
		t.Errorf("prompt message mismatch")
	}
	if parsed.Steps[0].Prompt.Secret != true {
		t.Error("secret flag mismatch")
	}
}

func TestValidateSetupSpec_Valid(t *testing.T) {
	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{
				ID: "step1", Name: "Step 1", Type: "prompt", Required: true,
				Prompt: &PromptConfig{Message: "Enter value:"},
			},
			{
				ID: "step2", Name: "Step 2", Type: "select", Required: true,
				DependsOn: []string{"step1"},
				Select: &SelectConfig{
					Options: []SelectOption{{Value: "a", Label: "A"}},
				},
			},
		},
	}
	if err := ValidateSetupSpec(spec); err != nil {
		t.Errorf("expected valid spec, got error: %v", err)
	}
}

func TestValidateSetupSpec_DuplicateIDs(t *testing.T) {
	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{ID: "dup", Name: "A", Type: "prompt", Prompt: &PromptConfig{Message: "a"}},
			{ID: "dup", Name: "B", Type: "prompt", Prompt: &PromptConfig{Message: "b"}},
		},
	}
	err := ValidateSetupSpec(spec)
	if err == nil {
		t.Fatal("expected error for duplicate IDs")
	}
}

func TestValidateSetupSpec_MissingDepRef(t *testing.T) {
	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{
				ID: "step1", Name: "Step 1", Type: "prompt",
				DependsOn: []string{"nonexistent"},
				Prompt:    &PromptConfig{Message: "a"},
			},
		},
	}
	err := ValidateSetupSpec(spec)
	if err == nil {
		t.Fatal("expected error for missing dependency reference")
	}
}

func TestValidateSetupSpec_CyclicDep(t *testing.T) {
	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{ID: "a", Name: "A", Type: "prompt", DependsOn: []string{"c"}, Prompt: &PromptConfig{Message: "a"}},
			{ID: "b", Name: "B", Type: "prompt", DependsOn: []string{"a"}, Prompt: &PromptConfig{Message: "b"}},
			{ID: "c", Name: "C", Type: "prompt", DependsOn: []string{"b"}, Prompt: &PromptConfig{Message: "c"}},
		},
	}
	err := ValidateSetupSpec(spec)
	if err == nil {
		t.Fatal("expected error for cyclic dependency")
	}
}

func TestValidateSetupSpec_MissingConfig(t *testing.T) {
	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{ID: "step1", Name: "Step 1", Type: "prompt"}, // no Prompt config
		},
	}
	err := ValidateSetupSpec(spec)
	if err == nil {
		t.Fatal("expected error for missing prompt config")
	}
}

func TestValidateSetupSpec_BadRegex(t *testing.T) {
	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{
				ID: "step1", Name: "Step 1", Type: "prompt",
				Prompt: &PromptConfig{
					Message:  "Enter value:",
					Validate: &ValidateConfig{Pattern: "[invalid"},
				},
			},
		},
	}
	err := ValidateSetupSpec(spec)
	if err == nil {
		t.Fatal("expected error for bad regex pattern")
	}
}

func TestTopologicalSort_Linear(t *testing.T) {
	steps := []SetupStep{
		{ID: "a"},
		{ID: "b", DependsOn: []string{"a"}},
		{ID: "c", DependsOn: []string{"b"}},
	}
	order, err := TopologicalSort(steps)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := []string{"a", "b", "c"}
	for i, id := range order {
		if id != expected[i] {
			t.Errorf("position %d: expected '%s', got '%s'", i, expected[i], id)
		}
	}
}

func TestTopologicalSort_Diamond(t *testing.T) {
	steps := []SetupStep{
		{ID: "a"},
		{ID: "b", DependsOn: []string{"a"}},
		{ID: "c", DependsOn: []string{"a"}},
		{ID: "d", DependsOn: []string{"b", "c"}},
	}
	order, err := TopologicalSort(steps)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(order) != 4 {
		t.Fatalf("expected 4 items, got %d", len(order))
	}
	// a must be first, d must be last
	if order[0] != "a" {
		t.Errorf("expected 'a' first, got '%s'", order[0])
	}
	if order[3] != "d" {
		t.Errorf("expected 'd' last, got '%s'", order[3])
	}
}

func TestTopologicalSort_NoDeps(t *testing.T) {
	steps := []SetupStep{
		{ID: "x"},
		{ID: "y"},
		{ID: "z"},
	}
	order, err := TopologicalSort(steps)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should maintain original order when no deps
	expected := []string{"x", "y", "z"}
	for i, id := range order {
		if id != expected[i] {
			t.Errorf("position %d: expected '%s', got '%s'", i, expected[i], id)
		}
	}
}

func TestTopologicalSort_Cycle(t *testing.T) {
	steps := []SetupStep{
		{ID: "a", DependsOn: []string{"b"}},
		{ID: "b", DependsOn: []string{"a"}},
	}
	_, err := TopologicalSort(steps)
	if err == nil {
		t.Fatal("expected error for cycle")
	}
}

func TestReadSetupState_NotFound(t *testing.T) {
	dir := t.TempDir()
	state, err := ReadSetupState(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if state == nil {
		t.Fatal("expected non-nil state")
	}
	if len(state.Steps) != 0 {
		t.Errorf("expected empty steps map, got %d entries", len(state.Steps))
	}
}

func TestWriteSetupState_RoundTrip(t *testing.T) {
	dir := t.TempDir()
	original := &SetupState{
		Version: "1",
		Steps: map[string]StepState{
			"step1": {Status: "completed", CompletedAt: "2026-01-01T00:00:00Z"},
			"step2": {Status: "failed", Error: "something went wrong"},
		},
	}

	if err := WriteSetupState(dir, original); err != nil {
		t.Fatalf("write error: %v", err)
	}

	state, err := ReadSetupState(dir)
	if err != nil {
		t.Fatalf("read error: %v", err)
	}

	if state.Version != "1" {
		t.Errorf("version mismatch")
	}
	if len(state.Steps) != 2 {
		t.Fatalf("expected 2 steps, got %d", len(state.Steps))
	}
	if state.Steps["step1"].Status != "completed" {
		t.Error("step1 status mismatch")
	}
	if state.Steps["step2"].Error != "something went wrong" {
		t.Error("step2 error mismatch")
	}
}

func TestGetSetupStatus_NoSetup(t *testing.T) {
	dir := t.TempDir()
	status, err := GetSetupStatus(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status.HasSetup {
		t.Error("expected has_setup=false")
	}
	if !status.IsComplete {
		t.Error("expected is_complete=true when no setup")
	}
}

func TestGetSetupStatus_AllComplete(t *testing.T) {
	dir := t.TempDir()

	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{ID: "s1", Name: "S1", Type: "prompt", Required: true, Prompt: &PromptConfig{Message: "a"}},
			{ID: "s2", Name: "S2", Type: "prompt", Required: true, Prompt: &PromptConfig{Message: "b"}},
		},
	}
	WriteSetupYaml(filepath.Join(dir, "setup.yaml"), spec)

	state := &SetupState{
		Version: "1",
		Steps: map[string]StepState{
			"s1": {Status: "completed", CompletedAt: "2026-01-01T00:00:00Z"},
			"s2": {Status: "completed", CompletedAt: "2026-01-01T00:00:00Z"},
		},
	}
	WriteSetupState(dir, state)

	status, err := GetSetupStatus(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !status.HasSetup {
		t.Error("expected has_setup=true")
	}
	if !status.IsComplete {
		t.Error("expected is_complete=true")
	}
	if status.CompletedN != 2 {
		t.Errorf("expected 2 completed, got %d", status.CompletedN)
	}
}

func TestGetSetupStatus_Pending(t *testing.T) {
	dir := t.TempDir()

	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{ID: "s1", Name: "S1", Type: "prompt", Required: true, Prompt: &PromptConfig{Message: "a"}},
			{ID: "s2", Name: "S2", Type: "prompt", Required: true, Prompt: &PromptConfig{Message: "b"}},
		},
	}
	WriteSetupYaml(filepath.Join(dir, "setup.yaml"), spec)

	state := &SetupState{
		Version: "1",
		Steps: map[string]StepState{
			"s1": {Status: "completed", CompletedAt: "2026-01-01T00:00:00Z"},
		},
	}
	WriteSetupState(dir, state)

	status, err := GetSetupStatus(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status.IsComplete {
		t.Error("expected is_complete=false")
	}
	if len(status.PendingSteps) != 1 {
		t.Fatalf("expected 1 pending step, got %d", len(status.PendingSteps))
	}
	if status.PendingSteps[0] != "s2" {
		t.Errorf("expected pending step 's2', got '%s'", status.PendingSteps[0])
	}
}

func TestGetSetupStatus_Expired(t *testing.T) {
	dir := t.TempDir()

	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{ID: "s1", Name: "S1", Type: "oauth2", Required: true,
				OAuth2: &OAuth2Config{AuthURL: "https://a.com", TokenURL: "https://t.com"}},
		},
	}
	WriteSetupYaml(filepath.Join(dir, "setup.yaml"), spec)

	pastTime := time.Now().Add(-1 * time.Hour).Format(time.RFC3339)
	state := &SetupState{
		Version: "1",
		Steps: map[string]StepState{
			"s1": {Status: "completed", CompletedAt: "2026-01-01T00:00:00Z", ExpiresAt: pastTime},
		},
	}
	WriteSetupState(dir, state)

	status, err := GetSetupStatus(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status.IsComplete {
		t.Error("expected is_complete=false for expired token")
	}
	if len(status.ExpiredSteps) != 1 {
		t.Fatalf("expected 1 expired step, got %d", len(status.ExpiredSteps))
	}
}

func TestGetSetupStatus_OptionalSkipped(t *testing.T) {
	dir := t.TempDir()

	spec := &SetupSpec{
		Version: "1",
		Steps: []SetupStep{
			{ID: "s1", Name: "S1", Type: "prompt", Required: true, Prompt: &PromptConfig{Message: "a"}},
			{ID: "s2", Name: "S2", Type: "prompt", Required: false, Prompt: &PromptConfig{Message: "b"}},
		},
	}
	WriteSetupYaml(filepath.Join(dir, "setup.yaml"), spec)

	state := &SetupState{
		Version: "1",
		Steps: map[string]StepState{
			"s1": {Status: "completed", CompletedAt: "2026-01-01T00:00:00Z"},
		},
	}
	WriteSetupState(dir, state)

	status, err := GetSetupStatus(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !status.IsComplete {
		t.Error("expected is_complete=true when only optional step is skipped")
	}
}

func TestHasSetup_True(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "setup.yaml"), []byte("version: '1'"), 0644)
	if !HasSetup(dir) {
		t.Error("expected HasSetup=true")
	}
}

func TestHasSetup_False(t *testing.T) {
	dir := t.TempDir()
	if HasSetup(dir) {
		t.Error("expected HasSetup=false")
	}
}
