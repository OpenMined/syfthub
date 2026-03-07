package setupflow

import (
	"encoding/json"
	"testing"
)

func TestResolveTemplate_StepValue(t *testing.T) {
	ctx := &SetupContext{
		StepOutputs: map[string]*StepResult{
			"foo": {Value: "hello"},
		},
	}
	result, err := ResolveTemplate("{{steps.foo.value}}", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "hello" {
		t.Errorf("expected 'hello', got '%s'", result)
	}
}

func TestResolveTemplate_StepOutput(t *testing.T) {
	ctx := &SetupContext{
		StepOutputs: map[string]*StepResult{
			"foo": {
				Outputs: map[string]string{"API_KEY": "abc123"},
			},
		},
	}
	result, err := ResolveTemplate("{{steps.foo.outputs.API_KEY}}", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "abc123" {
		t.Errorf("expected 'abc123', got '%s'", result)
	}
}

func TestResolveTemplate_StepResponse(t *testing.T) {
	ctx := &SetupContext{
		StepOutputs: map[string]*StepResult{
			"foo": {
				Response: json.RawMessage(`{"result":{"id":"xyz"}}`),
			},
		},
	}
	result, err := ResolveTemplate("{{steps.foo.response.result.id}}", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "xyz" {
		t.Errorf("expected 'xyz', got '%s'", result)
	}
}

func TestResolveTemplate_ContextVars(t *testing.T) {
	ctx := &SetupContext{
		HubURL:      "https://hub.example.com",
		Slug:        "my-endpoint",
		Username:    "alice",
		StepOutputs: map[string]*StepResult{},
	}

	tests := []struct {
		tmpl     string
		expected string
	}{
		{"{{context.hub_url}}", "https://hub.example.com"},
		{"{{context.endpoint_slug}}", "my-endpoint"},
		{"{{context.username}}", "alice"},
	}

	for _, tt := range tests {
		result, err := ResolveTemplate(tt.tmpl, ctx)
		if err != nil {
			t.Errorf("template %s: unexpected error: %v", tt.tmpl, err)
			continue
		}
		if result != tt.expected {
			t.Errorf("template %s: expected '%s', got '%s'", tt.tmpl, tt.expected, result)
		}
	}
}

func TestResolveTemplate_EnvVar(t *testing.T) {
	// Override getEnvVar for test
	orig := getEnvVar
	defer func() { getEnvVar = orig }()
	getEnvVar = func(name string) string {
		if name == "HOME" {
			return "/home/test"
		}
		return ""
	}

	ctx := &SetupContext{StepOutputs: map[string]*StepResult{}}
	result, err := ResolveTemplate("{{env.HOME}}", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "/home/test" {
		t.Errorf("expected '/home/test', got '%s'", result)
	}
}

func TestResolveTemplate_NestedJSON(t *testing.T) {
	ctx := &SetupContext{
		StepOutputs: map[string]*StepResult{
			"api": {
				Response: json.RawMessage(`{"data":{"items":[{"name":"first"},{"name":"second"}]}}`),
			},
		},
	}
	result, err := ResolveTemplate("{{steps.api.response.data.items[0].name}}", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "first" {
		t.Errorf("expected 'first', got '%s'", result)
	}
}

func TestResolveTemplate_MissingRef(t *testing.T) {
	ctx := &SetupContext{StepOutputs: map[string]*StepResult{}}
	_, err := ResolveTemplate("{{steps.nonexistent.value}}", ctx)
	if err == nil {
		t.Fatal("expected error for missing step reference")
	}
}

func TestResolveTemplate_MultipleRefs(t *testing.T) {
	ctx := &SetupContext{
		Username: "alice",
		StepOutputs: map[string]*StepResult{
			"auth": {
				Outputs: map[string]string{"TOKEN": "tok123"},
			},
		},
	}
	result, err := ResolveTemplate("Bearer {{steps.auth.outputs.TOKEN}} for {{context.username}}", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := "Bearer tok123 for alice"
	if result != expected {
		t.Errorf("expected '%s', got '%s'", expected, result)
	}
}

func TestResolveTemplate_NoRefs(t *testing.T) {
	ctx := &SetupContext{StepOutputs: map[string]*StepResult{}}
	result, err := ResolveTemplate("plain string", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "plain string" {
		t.Errorf("expected 'plain string', got '%s'", result)
	}
}

func TestResolveTemplate_ArrayIndex(t *testing.T) {
	ctx := &SetupContext{
		StepOutputs: map[string]*StepResult{
			"api": {
				Response: json.RawMessage(`{"channels":[{"id":"c1"},{"id":"c2"},{"id":"c3"}]}`),
			},
		},
	}
	result, err := ResolveTemplate("{{steps.api.response.channels[2].id}}", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "c3" {
		t.Errorf("expected 'c3', got '%s'", result)
	}
}

func TestExtractJSONPath_Simple(t *testing.T) {
	data := json.RawMessage(`{"name":"hello"}`)
	result, err := extractJSONPath(data, "name")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "hello" {
		t.Errorf("expected 'hello', got '%s'", result)
	}
}

func TestExtractJSONPath_Nested(t *testing.T) {
	data := json.RawMessage(`{"result":{"username":"bot"}}`)
	result, err := extractJSONPath(data, "result.username")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "bot" {
		t.Errorf("expected 'bot', got '%s'", result)
	}
}

func TestExtractJSONPath_Array(t *testing.T) {
	data := json.RawMessage(`{"items":[{"id":"a"},{"id":"b"}]}`)
	result, err := extractJSONPath(data, "items[0].id")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "a" {
		t.Errorf("expected 'a', got '%s'", result)
	}
}

func TestExtractJSONPath_Missing(t *testing.T) {
	data := json.RawMessage(`{"name":"hello"}`)
	_, err := extractJSONPath(data, "missing")
	if err == nil {
		t.Fatal("expected error for missing key")
	}
}
