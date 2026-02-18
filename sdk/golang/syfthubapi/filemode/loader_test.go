package filemode

import (
	"bytes"
	"log/slog"
	"os"
	"path/filepath"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestNewLoader(t *testing.T) {
	t.Run("with logger", func(t *testing.T) {
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		loader := NewLoader("/tmp/endpoints", logger)

		if loader == nil {
			t.Fatal("loader is nil")
		}
		if loader.basePath != "/tmp/endpoints" {
			t.Errorf("basePath = %q", loader.basePath)
		}
	})

	t.Run("without logger", func(t *testing.T) {
		loader := NewLoader("/tmp/endpoints", nil)

		if loader == nil {
			t.Fatal("loader is nil")
		}
		if loader.logger == nil {
			t.Error("logger should be set to default")
		}
	})
}

func TestLoaderLoadEndpoint(t *testing.T) {
	// Create temp directory structure
	tmpDir, err := os.MkdirTemp("", "loader_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	t.Run("success with all fields", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "test-endpoint")
		os.MkdirAll(endpointDir, 0755)

		// Create README.md with frontmatter
		readme := `---
slug: test-ep
name: Test Endpoint
type: model
description: A test endpoint
enabled: true
version: "1.0.0"
env:
  required: []
  optional: []
runtime:
  mode: subprocess
  timeout: 60
  workers: 2
---

# Test Endpoint

This is the description.
`
		os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte(readme), 0644)

		// Create runner.py
		os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte("def handler(): pass"), 0644)

		loader := NewLoader(tmpDir, nil)
		endpoint, err := loader.LoadEndpoint(endpointDir)

		if err != nil {
			t.Fatalf("LoadEndpoint error: %v", err)
		}

		if endpoint.Config.Slug != "test-ep" {
			t.Errorf("Slug = %q", endpoint.Config.Slug)
		}
		if endpoint.Config.Name != "Test Endpoint" {
			t.Errorf("Name = %q", endpoint.Config.Name)
		}
		if endpoint.Config.Type != "model" {
			t.Errorf("Type = %q", endpoint.Config.Type)
		}
		if endpoint.Config.Runtime.Timeout != 60 {
			t.Errorf("Timeout = %d", endpoint.Config.Runtime.Timeout)
		}
		if endpoint.Config.Runtime.Workers != 2 {
			t.Errorf("Workers = %d", endpoint.Config.Runtime.Workers)
		}
		if endpoint.ReadmeBody != "# Test Endpoint\n\nThis is the description." {
			t.Errorf("ReadmeBody = %q", endpoint.ReadmeBody)
		}
	})

	t.Run("missing README.md", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "no-readme")
		os.MkdirAll(endpointDir, 0755)
		os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte(""), 0644)

		loader := NewLoader(tmpDir, nil)
		_, err := loader.LoadEndpoint(endpointDir)

		if err == nil {
			t.Fatal("expected error for missing README.md")
		}
	})

	t.Run("missing runner.py", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "no-runner")
		os.MkdirAll(endpointDir, 0755)
		readme := `---
name: Test
type: model
---
`
		os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte(readme), 0644)

		loader := NewLoader(tmpDir, nil)
		_, err := loader.LoadEndpoint(endpointDir)

		if err == nil {
			t.Fatal("expected error for missing runner.py")
		}
	})

	t.Run("defaults slug to directory name", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "my-endpoint")
		os.MkdirAll(endpointDir, 0755)

		readme := `---
name: My Endpoint
type: data_source
---
`
		os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte(readme), 0644)
		os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte(""), 0644)

		loader := NewLoader(tmpDir, nil)
		endpoint, err := loader.LoadEndpoint(endpointDir)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if endpoint.Config.Slug != "my-endpoint" {
			t.Errorf("Slug = %q, want 'my-endpoint'", endpoint.Config.Slug)
		}
	})

	t.Run("defaults enabled to true", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "default-enabled")
		os.MkdirAll(endpointDir, 0755)

		readme := `---
name: Test
type: model
---
`
		os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte(readme), 0644)
		os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte(""), 0644)

		loader := NewLoader(tmpDir, nil)
		endpoint, err := loader.LoadEndpoint(endpointDir)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if endpoint.Config.Enabled == nil || !*endpoint.Config.Enabled {
			t.Error("Enabled should default to true")
		}
	})

	t.Run("explicit enabled false", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "disabled-ep")
		os.MkdirAll(endpointDir, 0755)

		readme := `---
name: Disabled
type: model
enabled: false
---
`
		os.WriteFile(filepath.Join(endpointDir, "README.md"), []byte(readme), 0644)
		os.WriteFile(filepath.Join(endpointDir, "runner.py"), []byte(""), 0644)

		loader := NewLoader(tmpDir, nil)
		endpoint, err := loader.LoadEndpoint(endpointDir)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if endpoint.Config.Enabled == nil || *endpoint.Config.Enabled {
			t.Error("Enabled should be false")
		}
	})
}

func TestLoaderLoadAll(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "loader_loadall_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	t.Run("loads multiple endpoints", func(t *testing.T) {
		// Create endpoint 1
		ep1Dir := filepath.Join(tmpDir, "ep1")
		os.MkdirAll(ep1Dir, 0755)
		os.WriteFile(filepath.Join(ep1Dir, "README.md"), []byte("---\nname: EP1\ntype: model\n---\n"), 0644)
		os.WriteFile(filepath.Join(ep1Dir, "runner.py"), []byte(""), 0644)

		// Create endpoint 2
		ep2Dir := filepath.Join(tmpDir, "ep2")
		os.MkdirAll(ep2Dir, 0755)
		os.WriteFile(filepath.Join(ep2Dir, "README.md"), []byte("---\nname: EP2\ntype: data_source\n---\n"), 0644)
		os.WriteFile(filepath.Join(ep2Dir, "runner.py"), []byte(""), 0644)

		loader := NewLoader(tmpDir, nil)
		endpoints, err := loader.LoadAll()

		if err != nil {
			t.Fatalf("LoadAll error: %v", err)
		}

		if len(endpoints) != 2 {
			t.Errorf("len(endpoints) = %d, want 2", len(endpoints))
		}
	})

	t.Run("skips hidden directories", func(t *testing.T) {
		// Create hidden directory
		hiddenDir := filepath.Join(tmpDir, ".hidden")
		os.MkdirAll(hiddenDir, 0755)
		os.WriteFile(filepath.Join(hiddenDir, "README.md"), []byte("---\nname: Hidden\ntype: model\n---\n"), 0644)
		os.WriteFile(filepath.Join(hiddenDir, "runner.py"), []byte(""), 0644)

		loader := NewLoader(tmpDir, nil)
		endpoints, _ := loader.LoadAll()

		for _, ep := range endpoints {
			if ep.Config.Name == "Hidden" {
				t.Error("should skip hidden directories")
			}
		}
	})

	t.Run("skips __pycache__", func(t *testing.T) {
		pycacheDir := filepath.Join(tmpDir, "__pycache__")
		os.MkdirAll(pycacheDir, 0755)

		loader := NewLoader(tmpDir, nil)
		endpoints, _ := loader.LoadAll()

		for _, ep := range endpoints {
			if ep.Dir == pycacheDir {
				t.Error("should skip __pycache__ directory")
			}
		}
	})

	t.Run("handles missing base directory", func(t *testing.T) {
		loader := NewLoader("/nonexistent/path", nil)
		_, err := loader.LoadAll()

		if err == nil {
			t.Fatal("expected error for missing directory")
		}
	})
}

func TestParseReadme(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "parse_readme_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	loader := NewLoader(tmpDir, nil)

	t.Run("valid frontmatter", func(t *testing.T) {
		path := filepath.Join(tmpDir, "valid.md")
		content := `---
name: Valid
type: model
description: A valid endpoint
---

# Body Content

Some markdown.
`
		os.WriteFile(path, []byte(content), 0644)

		config, body, err := loader.parseReadme(path)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if config.Name != "Valid" {
			t.Errorf("Name = %q", config.Name)
		}
		if config.Type != "model" {
			t.Errorf("Type = %q", config.Type)
		}
		if body != "# Body Content\n\nSome markdown." {
			t.Errorf("body = %q", body)
		}
	})

	t.Run("empty file", func(t *testing.T) {
		path := filepath.Join(tmpDir, "empty.md")
		os.WriteFile(path, []byte(""), 0644)

		_, _, err := loader.parseReadme(path)
		if err == nil {
			t.Fatal("expected error for empty file")
		}
	})

	t.Run("missing frontmatter delimiter", func(t *testing.T) {
		path := filepath.Join(tmpDir, "no-delimiter.md")
		os.WriteFile(path, []byte("# Just markdown"), 0644)

		_, _, err := loader.parseReadme(path)
		if err == nil {
			t.Fatal("expected error for missing frontmatter")
		}
	})

	t.Run("unclosed frontmatter", func(t *testing.T) {
		path := filepath.Join(tmpDir, "unclosed.md")
		content := `---
name: Unclosed
type: model
# No closing ---
`
		os.WriteFile(path, []byte(content), 0644)

		_, _, err := loader.parseReadme(path)
		if err == nil {
			t.Fatal("expected error for unclosed frontmatter")
		}
	})

	t.Run("missing name field", func(t *testing.T) {
		path := filepath.Join(tmpDir, "no-name.md")
		content := `---
type: model
---
`
		os.WriteFile(path, []byte(content), 0644)

		_, _, err := loader.parseReadme(path)
		if err == nil {
			t.Fatal("expected error for missing name")
		}
	})

	t.Run("missing type field", func(t *testing.T) {
		path := filepath.Join(tmpDir, "no-type.md")
		content := `---
name: No Type
---
`
		os.WriteFile(path, []byte(content), 0644)

		_, _, err := loader.parseReadme(path)
		if err == nil {
			t.Fatal("expected error for missing type")
		}
	})

	t.Run("invalid type", func(t *testing.T) {
		path := filepath.Join(tmpDir, "bad-type.md")
		content := `---
name: Bad Type
type: invalid_type
---
`
		os.WriteFile(path, []byte(content), 0644)

		_, _, err := loader.parseReadme(path)
		if err == nil {
			t.Fatal("expected error for invalid type")
		}
	})

	t.Run("invalid YAML", func(t *testing.T) {
		path := filepath.Join(tmpDir, "bad-yaml.md")
		content := `---
name: Bad YAML
type: [invalid yaml
---
`
		os.WriteFile(path, []byte(content), 0644)

		_, _, err := loader.parseReadme(path)
		if err == nil {
			t.Fatal("expected error for invalid YAML")
		}
	})
}

func TestLoadEnvVars(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "env_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	loader := NewLoader(tmpDir, nil)

	t.Run("loads .env file", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "with-env")
		os.MkdirAll(endpointDir, 0755)

		envContent := `FOO=bar
BAZ=qux
# Comment line
QUOTED="hello world"
SINGLE='single quoted'
`
		os.WriteFile(filepath.Join(endpointDir, ".env"), []byte(envContent), 0644)

		envConfig := &EnvConfig{}
		vars, err := loader.loadEnvVars(endpointDir, envConfig)

		if err != nil {
			t.Fatalf("error: %v", err)
		}

		varMap := envVarsToMap(vars)
		if varMap["FOO"] != "bar" {
			t.Errorf("FOO = %q", varMap["FOO"])
		}
		if varMap["BAZ"] != "qux" {
			t.Errorf("BAZ = %q", varMap["BAZ"])
		}
		if varMap["QUOTED"] != "hello world" {
			t.Errorf("QUOTED = %q", varMap["QUOTED"])
		}
	})

	t.Run("handles missing .env file", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "no-env")
		os.MkdirAll(endpointDir, 0755)

		envConfig := &EnvConfig{}
		vars, err := loader.loadEnvVars(endpointDir, envConfig)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if len(vars) != 0 {
			t.Errorf("expected no vars, got %d", len(vars))
		}
	})

	t.Run("inherits from system env", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "inherit-env")
		os.MkdirAll(endpointDir, 0755)

		t.Setenv("INHERITED_VAR", "inherited_value")

		envConfig := &EnvConfig{
			Inherit: []string{"INHERITED_VAR"},
		}
		vars, err := loader.loadEnvVars(endpointDir, envConfig)

		if err != nil {
			t.Fatalf("error: %v", err)
		}

		varMap := envVarsToMap(vars)
		if varMap["INHERITED_VAR"] != "inherited_value" {
			t.Errorf("INHERITED_VAR = %q", varMap["INHERITED_VAR"])
		}
	})

	t.Run("missing required env var", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "missing-required")
		os.MkdirAll(endpointDir, 0755)

		// Clear the env var to ensure it's not set
		os.Unsetenv("MISSING_REQUIRED_VAR_XYZ")

		envConfig := &EnvConfig{
			Required: []string{"MISSING_REQUIRED_VAR_XYZ"},
		}
		_, err := loader.loadEnvVars(endpointDir, envConfig)

		if err == nil {
			t.Fatal("expected error for missing required var")
		}
	})
}

func TestLoadPolicies(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "policy_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	loader := NewLoader(tmpDir, nil)

	t.Run("no policy directory", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "no-policies")
		os.MkdirAll(endpointDir, 0755)

		policies, store, err := loader.loadPolicies(endpointDir)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if policies != nil {
			t.Error("expected nil policies")
		}
		if store != nil {
			t.Error("expected nil store")
		}
	})

	t.Run("loads policy files", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "with-policies")
		policyDir := filepath.Join(endpointDir, "policy")
		os.MkdirAll(policyDir, 0755)

		policy1 := `name: rate_limit
type: rate_limit
config:
  requests_per_minute: 10
`
		os.WriteFile(filepath.Join(policyDir, "rate_limit.yaml"), []byte(policy1), 0644)

		policies, store, err := loader.loadPolicies(endpointDir)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if len(policies) != 1 {
			t.Errorf("len(policies) = %d", len(policies))
		}
		if policies[0].Name != "rate_limit" {
			t.Errorf("Name = %q", policies[0].Name)
		}
		if store == nil {
			t.Error("expected store config")
		}
	})

	t.Run("normalizes policy types", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "pascal-case")
		policyDir := filepath.Join(endpointDir, "policy")
		os.MkdirAll(policyDir, 0755)

		policy := `name: access_group
type: AccessGroupPolicy
config:
  allowed_groups:
    - admin
`
		os.WriteFile(filepath.Join(policyDir, "access.yaml"), []byte(policy), 0644)

		policies, _, err := loader.loadPolicies(endpointDir)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if policies[0].Type != syfthubapi.PolicyTypeAccessGroup {
			t.Errorf("Type = %q, want %q", policies[0].Type, syfthubapi.PolicyTypeAccessGroup)
		}
	})

	t.Run("skips non-yaml files", func(t *testing.T) {
		endpointDir := filepath.Join(tmpDir, "mixed-files")
		policyDir := filepath.Join(endpointDir, "policy")
		os.MkdirAll(policyDir, 0755)

		os.WriteFile(filepath.Join(policyDir, "readme.txt"), []byte("not a policy"), 0644)
		os.WriteFile(filepath.Join(policyDir, "policy.yaml"), []byte("name: test\ntype: rate_limit\n"), 0644)

		policies, _, err := loader.loadPolicies(endpointDir)

		if err != nil {
			t.Fatalf("error: %v", err)
		}
		if len(policies) != 1 {
			t.Errorf("len(policies) = %d, want 1", len(policies))
		}
	})
}

func TestValidatePolicies(t *testing.T) {
	loader := NewLoader("/tmp", nil)

	t.Run("valid policies", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "policy1", Type: syfthubapi.PolicyTypeRateLimit},
			{Name: "policy2", Type: syfthubapi.PolicyTypeAccessGroup},
		}

		err := loader.validatePolicies(policies)
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
	})

	t.Run("missing name", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "", Type: syfthubapi.PolicyTypeRateLimit},
		}

		err := loader.validatePolicies(policies)
		if err == nil {
			t.Error("expected error for missing name")
		}
	})

	t.Run("duplicate name", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "same", Type: syfthubapi.PolicyTypeRateLimit},
			{Name: "same", Type: syfthubapi.PolicyTypeAccessGroup},
		}

		err := loader.validatePolicies(policies)
		if err == nil {
			t.Error("expected error for duplicate name")
		}
	})

	t.Run("missing type", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "policy", Type: ""},
		}

		err := loader.validatePolicies(policies)
		if err == nil {
			t.Error("expected error for missing type")
		}
	})

	t.Run("unknown type", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "policy", Type: "unknown_type"},
		}

		err := loader.validatePolicies(policies)
		if err == nil {
			t.Error("expected error for unknown type")
		}
	})

	t.Run("all_of requires policies list", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "composite", Type: syfthubapi.PolicyTypeAllOf, Config: map[string]any{}},
		}

		err := loader.validatePolicies(policies)
		if err == nil {
			t.Error("expected error for missing policies list")
		}
	})

	t.Run("all_of with valid refs", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "base1", Type: syfthubapi.PolicyTypeRateLimit},
			{Name: "base2", Type: syfthubapi.PolicyTypeAccessGroup},
			{Name: "composite", Type: syfthubapi.PolicyTypeAllOf, Config: map[string]any{
				"policies": []any{"base1", "base2"},
			}},
		}

		err := loader.validatePolicies(policies)
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
	})

	t.Run("all_of with undefined ref", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "composite", Type: syfthubapi.PolicyTypeAllOf, Config: map[string]any{
				"policies": []any{"nonexistent"},
			}},
		}

		err := loader.validatePolicies(policies)
		if err == nil {
			t.Error("expected error for undefined reference")
		}
	})

	t.Run("not requires policy ref", func(t *testing.T) {
		policies := []syfthubapi.PolicyConfig{
			{Name: "negation", Type: syfthubapi.PolicyTypeNot, Config: map[string]any{}},
		}

		err := loader.validatePolicies(policies)
		if err == nil {
			t.Error("expected error for missing policy ref")
		}
	})
}

func TestNormalizePolicyType(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"AccessGroupPolicy", syfthubapi.PolicyTypeAccessGroup},
		{"RateLimitPolicy", syfthubapi.PolicyTypeRateLimit},
		{"TokenLimitPolicy", syfthubapi.PolicyTypeTokenLimit},
		{"PromptFilterPolicy", syfthubapi.PolicyTypePromptFilter},
		{"AttributionPolicy", syfthubapi.PolicyTypeAttribution},
		{"ManualReviewPolicy", syfthubapi.PolicyTypeManualReview},
		{"TransactionPolicy", syfthubapi.PolicyTypeTransaction},
		{"CustomPolicy", syfthubapi.PolicyTypeCustom},
		{"AllOfPolicy", syfthubapi.PolicyTypeAllOf},
		{"AnyOfPolicy", syfthubapi.PolicyTypeAnyOf},
		{"NotPolicy", syfthubapi.PolicyTypeNot},
		// Already normalized
		{syfthubapi.PolicyTypeRateLimit, syfthubapi.PolicyTypeRateLimit},
		// Unknown type (returned as-is)
		{"unknown_type", "unknown_type"},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := normalizePolicyType(tt.input)
			if result != tt.expected {
				t.Errorf("normalizePolicyType(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestLoadDotEnv(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "dotenv_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	t.Run("parses basic format", func(t *testing.T) {
		path := filepath.Join(tmpDir, "basic.env")
		content := `KEY1=value1
KEY2=value2
`
		os.WriteFile(path, []byte(content), 0644)

		vars, err := loadDotEnv(path)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		m := envVarsToMap(vars)
		if m["KEY1"] != "value1" {
			t.Errorf("KEY1 = %q", m["KEY1"])
		}
		if m["KEY2"] != "value2" {
			t.Errorf("KEY2 = %q", m["KEY2"])
		}
	})

	t.Run("handles comments", func(t *testing.T) {
		path := filepath.Join(tmpDir, "comments.env")
		content := `# This is a comment
KEY=value
# Another comment
`
		os.WriteFile(path, []byte(content), 0644)

		vars, err := loadDotEnv(path)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if len(vars) != 1 {
			t.Errorf("len(vars) = %d, want 1", len(vars))
		}
	})

	t.Run("handles empty lines", func(t *testing.T) {
		path := filepath.Join(tmpDir, "empty-lines.env")
		content := `KEY1=value1

KEY2=value2
`
		os.WriteFile(path, []byte(content), 0644)

		vars, err := loadDotEnv(path)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		if len(vars) != 2 {
			t.Errorf("len(vars) = %d, want 2", len(vars))
		}
	})

	t.Run("handles quoted values", func(t *testing.T) {
		path := filepath.Join(tmpDir, "quoted.env")
		content := `DOUBLE="double quoted"
SINGLE='single quoted'
`
		os.WriteFile(path, []byte(content), 0644)

		vars, err := loadDotEnv(path)
		if err != nil {
			t.Fatalf("error: %v", err)
		}

		m := envVarsToMap(vars)
		if m["DOUBLE"] != "double quoted" {
			t.Errorf("DOUBLE = %q", m["DOUBLE"])
		}
		if m["SINGLE"] != "single quoted" {
			t.Errorf("SINGLE = %q", m["SINGLE"])
		}
	})
}

func TestEnvVarsToMap(t *testing.T) {
	vars := []string{
		"KEY1=value1",
		"KEY2=value2",
		"KEY3=value=with=equals",
	}

	m := envVarsToMap(vars)

	if m["KEY1"] != "value1" {
		t.Errorf("KEY1 = %q", m["KEY1"])
	}
	if m["KEY2"] != "value2" {
		t.Errorf("KEY2 = %q", m["KEY2"])
	}
	if m["KEY3"] != "value=with=equals" {
		t.Errorf("KEY3 = %q", m["KEY3"])
	}
}

func TestToEndpointType(t *testing.T) {
	tests := []struct {
		input    string
		expected syfthubapi.EndpointType
	}{
		{"model", syfthubapi.EndpointTypeModel},
		{"data_source", syfthubapi.EndpointTypeDataSource},
		{"unknown", syfthubapi.EndpointTypeModel}, // defaults to model
		{"", syfthubapi.EndpointTypeModel},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := ToEndpointType(tt.input)
			if result != tt.expected {
				t.Errorf("ToEndpointType(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}
