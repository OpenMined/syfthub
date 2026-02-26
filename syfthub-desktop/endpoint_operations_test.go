package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/openmined/syfthub-desktop-gui/internal/app"
)

// ============================================================================
// Slugify Tests
// ============================================================================

func TestSlugify(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"simple lowercase", "hello", "hello"},
		{"uppercase to lowercase", "Hello", "hello"},
		{"spaces to hyphens", "hello world", "hello-world"},
		{"underscores to hyphens", "hello_world", "hello-world"},
		{"mixed case and spaces", "My Cool Model", "my-cool-model"},
		{"special characters removed", "Hello@World!", "helloworld"},
		{"multiple spaces", "hello   world", "hello-world"},
		{"multiple hyphens collapsed", "hello--world", "hello-world"},
		{"leading/trailing hyphens trimmed", "-hello-", "hello"},
		{"numbers preserved", "model123", "model123"},
		{"complex name", "My Model v2.0", "my-model-v20"},
		{"empty string", "", ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := slugify(tt.input)
			if result != tt.expected {
				t.Errorf("slugify(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestSlugifyFilename(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"simple name", "rate limit", "rate-limit.yaml"},
		{"spaces to hyphens", "My Rate Limit Policy", "my-rate-limit-policy.yaml"},
		{"special chars removed", "Policy@#$Test", "policytest.yaml"},
		{"empty becomes default", "", "new-policy.yaml"},
		{"numbers preserved", "policy123", "policy123.yaml"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := slugifyFilename(tt.input)
			if result != tt.expected {
				t.Errorf("slugifyFilename(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

// ============================================================================
// Policy Template Generation Tests
// ============================================================================

func TestGeneratePolicyYAML(t *testing.T) {
	tests := []struct {
		name         string
		req          NewPolicyRequest
		wantContains []string
	}{
		{
			name:         "AccessGroupPolicy",
			req:          NewPolicyRequest{Name: "test-policy", Type: "AccessGroupPolicy"},
			wantContains: []string{"type: AccessGroupPolicy", "name: test-policy", "users:"},
		},
		{
			name:         "RateLimitPolicy",
			req:          NewPolicyRequest{Name: "rate-limit", Type: "RateLimitPolicy"},
			wantContains: []string{"type: RateLimitPolicy", "max_requests:", "window_seconds:"},
		},
		{
			name:         "TokenLimitPolicy",
			req:          NewPolicyRequest{Name: "token-limit", Type: "TokenLimitPolicy"},
			wantContains: []string{"type: TokenLimitPolicy", "max_tokens_per_request:"},
		},
		{
			name:         "PromptFilterPolicy",
			req:          NewPolicyRequest{Name: "filter", Type: "PromptFilterPolicy"},
			wantContains: []string{"type: PromptFilterPolicy", "patterns:"},
		},
		{
			name:         "AttributionPolicy",
			req:          NewPolicyRequest{Name: "attribution", Type: "AttributionPolicy"},
			wantContains: []string{"type: AttributionPolicy", "track_fields:"},
		},
		{
			name:         "ManualReviewPolicy",
			req:          NewPolicyRequest{Name: "review", Type: "ManualReviewPolicy"},
			wantContains: []string{"type: ManualReviewPolicy", "timeout_seconds:"},
		},
		{
			name:         "TransactionPolicy",
			req:          NewPolicyRequest{Name: "transaction", Type: "TransactionPolicy"},
			wantContains: []string{"type: TransactionPolicy", "cost_per_request:"},
		},
		{
			name:         "BundleSubscriptionPolicy",
			req:          NewPolicyRequest{Name: "pro-plan", Type: "BundleSubscriptionPolicy"},
			wantContains: []string{"type: BundleSubscriptionPolicy", "name: pro-plan", "plan_name:", "price:", "currency:", "billing_cycle:", "invoice_url:"},
		},
		{
			name: "AllOfPolicy with children",
			req: NewPolicyRequest{
				Name:          "all-of",
				Type:          "AllOfPolicy",
				ChildPolicies: []string{"policy-a", "policy-b"},
			},
			wantContains: []string{"type: AllOfPolicy", "policies:", "- policy-a", "- policy-b"},
		},
		{
			name: "AnyOfPolicy with children",
			req: NewPolicyRequest{
				Name:          "any-of",
				Type:          "AnyOfPolicy",
				ChildPolicies: []string{"policy-x"},
			},
			wantContains: []string{"type: AnyOfPolicy", "policies:", "- policy-x"},
		},
		{
			name: "NotPolicy",
			req: NewPolicyRequest{
				Name:          "not-policy",
				Type:          "NotPolicy",
				ChildPolicies: []string{"negated-policy"},
				DenyReason:    "Custom deny reason",
			},
			wantContains: []string{"type: NotPolicy", "policy: negated-policy", "deny_reason:"},
		},
		{
			name:         "Unknown type",
			req:          NewPolicyRequest{Name: "unknown", Type: "CustomPolicy"},
			wantContains: []string{"type: CustomPolicy", "name: unknown", "config: {}"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := generatePolicyYAML(tt.req)
			for _, want := range tt.wantContains {
				if !strings.Contains(result, want) {
					t.Errorf("generatePolicyYAML result missing %q\nGot:\n%s", want, result)
				}
			}
		})
	}
}

func TestGeneratePolicyYAMLDefaults(t *testing.T) {
	// Test AllOfPolicy without child policies uses defaults
	req := NewPolicyRequest{Name: "test", Type: "AllOfPolicy"}
	result := generatePolicyYAML(req)
	if !strings.Contains(result, "policy_name_1") {
		t.Error("AllOfPolicy without children should use default policy names")
	}

	// Test NotPolicy without children
	req = NewPolicyRequest{Name: "test", Type: "NotPolicy"}
	result = generatePolicyYAML(req)
	if !strings.Contains(result, "policy_to_negate") {
		t.Error("NotPolicy without children should use default policy name")
	}
	if !strings.Contains(result, "Access denied by policy negation") {
		t.Error("NotPolicy without deny_reason should use default reason")
	}
}

// ============================================================================
// Runner Template Tests
// ============================================================================

func TestGetRunnerTemplate(t *testing.T) {
	// Test model template
	modelTemplate := getRunnerTemplate("model")
	if !strings.Contains(modelTemplate, "def handler(messages") {
		t.Error("model template should contain handler function")
	}
	if !strings.Contains(modelTemplate, "Echo:") {
		t.Error("model template should contain echo functionality")
	}

	// Test data_source template
	dataSourceTemplate := getRunnerTemplate("data_source")
	if !strings.Contains(dataSourceTemplate, "def query(request") {
		t.Error("data_source template should contain query function")
	}
	if !strings.Contains(dataSourceTemplate, "Data Source") {
		t.Error("data_source template should mention Data Source")
	}
}

// ============================================================================
// Env File Parsing Tests
// ============================================================================

func TestReadEnvFile(t *testing.T) {
	tempDir := t.TempDir()
	envPath := filepath.Join(tempDir, ".env")

	// Create test .env file
	content := `# This is a comment
KEY1=value1
KEY2=value2
KEY_WITH_SPACES="value with spaces"
KEY_SINGLE_QUOTES='single quoted'
EMPTY_LINE_ABOVE=test

# Another comment
`
	if err := os.WriteFile(envPath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	app := &App{}
	vars, err := app.readEnvFile(envPath)
	if err != nil {
		t.Fatalf("readEnvFile error: %v", err)
	}

	expected := map[string]string{
		"KEY1":              "value1",
		"KEY2":              "value2",
		"KEY_WITH_SPACES":   "value with spaces",
		"KEY_SINGLE_QUOTES": "single quoted",
		"EMPTY_LINE_ABOVE":  "test",
	}

	for _, v := range vars {
		if want, ok := expected[v.Key]; ok {
			if v.Value != want {
				t.Errorf("Key %q = %q, want %q", v.Key, v.Value, want)
			}
			delete(expected, v.Key)
		}
	}

	if len(expected) > 0 {
		t.Errorf("Missing keys: %v", expected)
	}
}

func TestReadEnvFileNotExist(t *testing.T) {
	app := &App{}
	vars, err := app.readEnvFile("/nonexistent/path/.env")
	if err != nil {
		t.Errorf("readEnvFile should not error for nonexistent file: %v", err)
	}
	if len(vars) != 0 {
		t.Errorf("vars should be empty for nonexistent file, got %d items", len(vars))
	}
}

func TestWriteEnvFile(t *testing.T) {
	tempDir := t.TempDir()
	envPath := filepath.Join(tempDir, ".env")

	app := &App{}
	vars := []EnvVar{
		{Key: "SIMPLE", Value: "value"},
		{Key: "WITH_SPACES", Value: "value with spaces"},
		{Key: "WITH_QUOTES", Value: `value "quoted"`},
	}

	if err := app.writeEnvFile(envPath, vars); err != nil {
		t.Fatalf("writeEnvFile error: %v", err)
	}

	// Read back and verify
	content, err := os.ReadFile(envPath)
	if err != nil {
		t.Fatalf("Failed to read file: %v", err)
	}

	contentStr := string(content)
	if !strings.Contains(contentStr, "SIMPLE=value") {
		t.Error("File should contain SIMPLE=value")
	}
	if !strings.Contains(contentStr, `WITH_SPACES="value with spaces"`) {
		t.Error("File should quote values with spaces")
	}
}

// ============================================================================
// Dependency Parsing Tests
// ============================================================================

func TestReadDependencies(t *testing.T) {
	tempDir := t.TempDir()
	pyprojectPath := filepath.Join(tempDir, "pyproject.toml")

	// Create test pyproject.toml
	content := `[project]
name = "test-endpoint"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0",
    "numpy==1.24.0",
    "pandas",
]

[tool.pytest]
testpaths = ["tests"]
`
	if err := os.WriteFile(pyprojectPath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	app := &App{}
	deps, err := app.readDependencies(pyprojectPath)
	if err != nil {
		t.Fatalf("readDependencies error: %v", err)
	}

	if len(deps) != 3 {
		t.Errorf("Expected 3 dependencies, got %d", len(deps))
	}

	// Check specific dependencies
	found := make(map[string]string)
	for _, dep := range deps {
		found[dep.Package] = dep.Version
	}

	if found["requests"] != "2.28.0" {
		t.Errorf("requests version = %q, want %q", found["requests"], "2.28.0")
	}
	if found["numpy"] != "1.24.0" {
		t.Errorf("numpy version = %q, want %q", found["numpy"], "1.24.0")
	}
	if found["pandas"] != "" {
		t.Errorf("pandas should have no version constraint, got %q", found["pandas"])
	}
}

func TestReadDependenciesNotExist(t *testing.T) {
	app := &App{}
	deps, err := app.readDependencies("/nonexistent/pyproject.toml")
	if err != nil {
		t.Errorf("readDependencies should not error for nonexistent file: %v", err)
	}
	if len(deps) != 0 {
		t.Errorf("deps should be empty for nonexistent file, got %d items", len(deps))
	}
}

// ============================================================================
// README Frontmatter Tests
// ============================================================================

func TestParseReadmeFrontmatter(t *testing.T) {
	tempDir := t.TempDir()
	readmePath := filepath.Join(tempDir, "README.md")

	enabled := true
	content := `---
slug: my-endpoint
name: My Endpoint
description: A test endpoint
type: model
version: "1.0.0"
enabled: true
---

# My Endpoint

This is the body content.

## Usage

Use it wisely.
`
	if err := os.WriteFile(readmePath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	app := &App{}
	fm, body, err := app.parseReadmeFrontmatter(readmePath)
	if err != nil {
		t.Fatalf("parseReadmeFrontmatter error: %v", err)
	}

	if fm.Slug != "my-endpoint" {
		t.Errorf("Slug = %q, want %q", fm.Slug, "my-endpoint")
	}
	if fm.Name != "My Endpoint" {
		t.Errorf("Name = %q, want %q", fm.Name, "My Endpoint")
	}
	if fm.Description != "A test endpoint" {
		t.Errorf("Description = %q, want %q", fm.Description, "A test endpoint")
	}
	if fm.Type != "model" {
		t.Errorf("Type = %q, want %q", fm.Type, "model")
	}
	if fm.Version != "1.0.0" {
		t.Errorf("Version = %q, want %q", fm.Version, "1.0.0")
	}
	if fm.Enabled == nil || *fm.Enabled != enabled {
		t.Errorf("Enabled = %v, want %v", fm.Enabled, &enabled)
	}

	if !strings.Contains(body, "# My Endpoint") {
		t.Error("body should contain markdown heading")
	}
	if !strings.Contains(body, "Use it wisely") {
		t.Error("body should contain body content")
	}
}

func TestParseReadmeFrontmatterNoFrontmatter(t *testing.T) {
	tempDir := t.TempDir()
	readmePath := filepath.Join(tempDir, "README.md")

	content := `# Just a README

No frontmatter here.
`
	if err := os.WriteFile(readmePath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	app := &App{}
	_, _, err := app.parseReadmeFrontmatter(readmePath)
	if err == nil {
		t.Error("parseReadmeFrontmatter should error when no frontmatter")
	}
}

func TestParseReadmeFrontmatterUnclosed(t *testing.T) {
	tempDir := t.TempDir()
	readmePath := filepath.Join(tempDir, "README.md")

	content := `---
slug: test
name: Test

# No closing ---
Body content here.
`
	if err := os.WriteFile(readmePath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	app := &App{}
	_, _, err := app.parseReadmeFrontmatter(readmePath)
	if err == nil {
		t.Error("parseReadmeFrontmatter should error for unclosed frontmatter")
	}
}

func TestUpdateReadmeFrontmatter(t *testing.T) {
	tempDir := t.TempDir()
	readmePath := filepath.Join(tempDir, "README.md")

	initialContent := `---
slug: my-endpoint
name: Old Name
type: model
---

# Body Content

Keep this.
`
	if err := os.WriteFile(readmePath, []byte(initialContent), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	app := &App{}
	updates := map[string]interface{}{
		"name":        "New Name",
		"description": "Added description",
	}

	if err := app.updateReadmeFrontmatter(readmePath, updates); err != nil {
		t.Fatalf("updateReadmeFrontmatter error: %v", err)
	}

	// Read and verify
	content, _ := os.ReadFile(readmePath)
	contentStr := string(content)

	if !strings.Contains(contentStr, "name: New Name") {
		t.Error("Should contain updated name")
	}
	if !strings.Contains(contentStr, "description: Added description") {
		t.Error("Should contain added description")
	}
	if !strings.Contains(contentStr, "slug: my-endpoint") {
		t.Error("Should preserve existing slug")
	}
	if !strings.Contains(contentStr, "# Body Content") {
		t.Error("Should preserve body content")
	}
}

// ============================================================================
// Policies YAML Tests
// ============================================================================

func TestParsePoliciesYaml(t *testing.T) {
	tempDir := t.TempDir()
	policiesPath := filepath.Join(tempDir, "policies.yaml")

	content := `version: "1.0"
store:
  type: sqlite
  path: .policy_store.db
policies:
  - name: rate-limit
    type: RateLimitPolicy
    config:
      max_requests: 100
  - name: access-group
    type: AccessGroupPolicy
    config:
      users:
        - user@example.com
`
	if err := os.WriteFile(policiesPath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write test file: %v", err)
	}

	app := &App{}
	policies, version, err := app.parsePoliciesYaml(policiesPath)
	if err != nil {
		t.Fatalf("parsePoliciesYaml error: %v", err)
	}

	if version != "1.0" {
		t.Errorf("version = %q, want %q", version, "1.0")
	}

	if len(policies) != 2 {
		t.Fatalf("Expected 2 policies, got %d", len(policies))
	}

	if policies[0].Name != "rate-limit" {
		t.Errorf("First policy name = %q, want %q", policies[0].Name, "rate-limit")
	}
	if policies[0].Type != "RateLimitPolicy" {
		t.Errorf("First policy type = %q, want %q", policies[0].Type, "RateLimitPolicy")
	}
}

func TestParsePoliciesYamlNotExist(t *testing.T) {
	app := &App{}
	_, _, err := app.parsePoliciesYaml("/nonexistent/policies.yaml")
	if err == nil {
		t.Error("parsePoliciesYaml should error for nonexistent file")
	}
}

// ============================================================================
// Type Definitions Tests
// ============================================================================

func TestEndpointDetailJSON(t *testing.T) {
	detail := EndpointDetail{
		Slug:        "test-endpoint",
		Name:        "Test Endpoint",
		Description: "A test endpoint",
		Type:        "model",
		Version:     "1.0.0",
		Enabled:     true,
		HasReadme:   true,
		HasPolicies: false,
		DepsCount:   5,
		EnvCount:    3,
	}

	// Just verify the struct can be created correctly
	if detail.Slug != "test-endpoint" {
		t.Errorf("Slug = %q, want %q", detail.Slug, "test-endpoint")
	}
}

func TestEnvVarStruct(t *testing.T) {
	envVar := EnvVar{Key: "API_KEY", Value: "secret123"}
	if envVar.Key != "API_KEY" {
		t.Errorf("Key = %q, want %q", envVar.Key, "API_KEY")
	}
	if envVar.Value != "secret123" {
		t.Errorf("Value = %q, want %q", envVar.Value, "secret123")
	}
}

func TestDependencyStruct(t *testing.T) {
	dep := Dependency{Package: "requests", Version: "2.28.0"}
	if dep.Package != "requests" {
		t.Errorf("Package = %q, want %q", dep.Package, "requests")
	}
	if dep.Version != "2.28.0" {
		t.Errorf("Version = %q, want %q", dep.Version, "2.28.0")
	}
}

func TestPolicyStruct(t *testing.T) {
	policy := Policy{
		Name:   "rate-limit",
		Type:   "RateLimitPolicy",
		Config: map[string]interface{}{"max_requests": 100},
	}
	if policy.Name != "rate-limit" {
		t.Errorf("Name = %q, want %q", policy.Name, "rate-limit")
	}
	if policy.Type != "RateLimitPolicy" {
		t.Errorf("Type = %q, want %q", policy.Type, "RateLimitPolicy")
	}
}

func TestPoliciesFileStruct(t *testing.T) {
	pf := PoliciesFile{
		Version: "1.0",
		Store:   map[string]interface{}{"type": "sqlite"},
		Policies: []Policy{
			{Name: "test", Type: "TestPolicy"},
		},
	}
	if pf.Version != "1.0" {
		t.Errorf("Version = %q, want %q", pf.Version, "1.0")
	}
	if len(pf.Policies) != 1 {
		t.Errorf("len(Policies) = %d, want 1", len(pf.Policies))
	}
}

func TestOverviewDataStruct(t *testing.T) {
	overview := OverviewData{
		Name:        "My Endpoint",
		Description: "Description here",
		Type:        "model",
		Version:     "2.0.0",
	}
	if overview.Name != "My Endpoint" {
		t.Errorf("Name = %q, want %q", overview.Name, "My Endpoint")
	}
}

func TestCreateEndpointRequestStruct(t *testing.T) {
	req := CreateEndpointRequest{
		Name:        "New Model",
		Type:        "model",
		Description: "A new model endpoint",
		Version:     "1.0.0",
	}
	if req.Name != "New Model" {
		t.Errorf("Name = %q, want %q", req.Name, "New Model")
	}
	if req.Type != "model" {
		t.Errorf("Type = %q, want %q", req.Type, "model")
	}
}

func TestPolicyFileInfoStruct(t *testing.T) {
	info := PolicyFileInfo{
		Filename: "rate-limit.yaml",
		Name:     "Rate Limit",
		Type:     "RateLimitPolicy",
	}
	if info.Filename != "rate-limit.yaml" {
		t.Errorf("Filename = %q, want %q", info.Filename, "rate-limit.yaml")
	}
}

func TestNewPolicyRequestStruct(t *testing.T) {
	req := NewPolicyRequest{
		Name:          "Composite Policy",
		Type:          "AllOfPolicy",
		ChildPolicies: []string{"policy-a", "policy-b"},
		DenyReason:    "Access denied",
	}
	if req.Name != "Composite Policy" {
		t.Errorf("Name = %q, want %q", req.Name, "Composite Policy")
	}
	if len(req.ChildPolicies) != 2 {
		t.Errorf("len(ChildPolicies) = %d, want 2", len(req.ChildPolicies))
	}
}

// ============================================================================
// Config-Only Function Tests (no Wails runtime dependency)
// ============================================================================

func TestGetRunnerCode(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	runnerContent := `def handler(messages, context=None):
    return "Hello, World!"
`
	runnerPath := filepath.Join(endpointDir, "runner.py")
	if err := os.WriteFile(runnerPath, []byte(runnerContent), 0644); err != nil {
		t.Fatalf("Failed to write runner.py: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	code, err := app.GetRunnerCode("test-endpoint")
	if err != nil {
		t.Fatalf("GetRunnerCode error: %v", err)
	}
	if code != runnerContent {
		t.Errorf("GetRunnerCode returned wrong content")
	}
}

func TestGetRunnerCodeNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.GetRunnerCode("test-endpoint")
	if err == nil {
		t.Error("GetRunnerCode should error when not configured")
	}
	if !strings.Contains(err.Error(), "not configured") {
		t.Errorf("Error should mention 'not configured', got: %v", err)
	}
}

func TestGetRunnerCodeNotFound(t *testing.T) {
	tempDir := t.TempDir()
	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	_, err := app.GetRunnerCode("nonexistent")
	if err == nil {
		t.Error("GetRunnerCode should error for nonexistent endpoint")
	}
}

func TestGetReadme(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	readmeContent := `---
slug: test-endpoint
name: Test Endpoint
---

# Test Endpoint

This is a test.
`
	readmePath := filepath.Join(endpointDir, "README.md")
	if err := os.WriteFile(readmePath, []byte(readmeContent), 0644); err != nil {
		t.Fatalf("Failed to write README.md: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	content, err := app.GetReadme("test-endpoint")
	if err != nil {
		t.Fatalf("GetReadme error: %v", err)
	}
	if content != readmeContent {
		t.Errorf("GetReadme returned wrong content")
	}
}

func TestGetReadmeNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.GetReadme("test-endpoint")
	if err == nil {
		t.Error("GetReadme should error when not configured")
	}
}

func TestGetReadmeNotFound(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	// Should return empty string for nonexistent README
	content, err := app.GetReadme("test-endpoint")
	if err != nil {
		t.Fatalf("GetReadme should not error for missing README: %v", err)
	}
	if content != "" {
		t.Errorf("GetReadme should return empty string for missing README, got: %q", content)
	}
}

func TestGetEnvironment(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	envContent := `API_KEY=secret123
DATABASE_URL=postgres://localhost/db
`
	envPath := filepath.Join(endpointDir, ".env")
	if err := os.WriteFile(envPath, []byte(envContent), 0644); err != nil {
		t.Fatalf("Failed to write .env: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	vars, err := app.GetEnvironment("test-endpoint")
	if err != nil {
		t.Fatalf("GetEnvironment error: %v", err)
	}
	if len(vars) != 2 {
		t.Errorf("Expected 2 env vars, got %d", len(vars))
	}
}

func TestGetEnvironmentNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.GetEnvironment("test-endpoint")
	if err == nil {
		t.Error("GetEnvironment should error when not configured")
	}
}

func TestGetDependencies(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	pyprojectContent := `[project]
name = "test-endpoint"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0",
    "numpy",
]
`
	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	if err := os.WriteFile(pyprojectPath, []byte(pyprojectContent), 0644); err != nil {
		t.Fatalf("Failed to write pyproject.toml: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	deps, err := app.GetDependencies("test-endpoint")
	if err != nil {
		t.Fatalf("GetDependencies error: %v", err)
	}
	if len(deps) != 2 {
		t.Errorf("Expected 2 dependencies, got %d", len(deps))
	}
}

func TestGetDependenciesNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.GetDependencies("test-endpoint")
	if err == nil {
		t.Error("GetDependencies should error when not configured")
	}
}

func TestGetPolicies(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	policiesContent := `version: "1.0"
store:
  type: sqlite
  path: .policy_store.db
policies:
  - name: rate-limit
    type: RateLimitPolicy
    config:
      max_requests: 100
`
	policiesPath := filepath.Join(endpointDir, "policies.yaml")
	if err := os.WriteFile(policiesPath, []byte(policiesContent), 0644); err != nil {
		t.Fatalf("Failed to write policies.yaml: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	policies, err := app.GetPolicies("test-endpoint")
	if err != nil {
		t.Fatalf("GetPolicies error: %v", err)
	}
	if len(policies) != 1 {
		t.Errorf("Expected 1 policy, got %d", len(policies))
	}
	if policies[0].Name != "rate-limit" {
		t.Errorf("Policy name = %q, want %q", policies[0].Name, "rate-limit")
	}
}

func TestGetPoliciesNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.GetPolicies("test-endpoint")
	if err == nil {
		t.Error("GetPolicies should error when not configured")
	}
}

func TestGetPoliciesNotFound(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	// Should return empty slice for missing policies.yaml
	policies, err := app.GetPolicies("test-endpoint")
	if err != nil {
		t.Fatalf("GetPolicies should not error for missing file: %v", err)
	}
	if len(policies) != 0 {
		t.Errorf("Expected empty policies, got %d", len(policies))
	}
}

func TestGetPoliciesYaml(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	policiesContent := `version: "1.0"
policies: []
`
	policiesPath := filepath.Join(endpointDir, "policies.yaml")
	if err := os.WriteFile(policiesPath, []byte(policiesContent), 0644); err != nil {
		t.Fatalf("Failed to write policies.yaml: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	content, err := app.GetPoliciesYaml("test-endpoint")
	if err != nil {
		t.Fatalf("GetPoliciesYaml error: %v", err)
	}
	if content != policiesContent {
		t.Errorf("GetPoliciesYaml returned wrong content")
	}
}

func TestGetPoliciesYamlNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.GetPoliciesYaml("test-endpoint")
	if err == nil {
		t.Error("GetPoliciesYaml should error when not configured")
	}
}

func TestGetPoliciesYamlNotFound(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	// Should return default template for missing policies.yaml
	content, err := app.GetPoliciesYaml("test-endpoint")
	if err != nil {
		t.Fatalf("GetPoliciesYaml should not error for missing file: %v", err)
	}
	if !strings.Contains(content, "policies: []") {
		t.Error("Default template should contain empty policies array")
	}
}

func TestCheckEndpointExists(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "existing-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	// Test existing endpoint
	slug, exists := app.CheckEndpointExists("Existing Endpoint")
	if slug != "existing-endpoint" {
		t.Errorf("slug = %q, want %q", slug, "existing-endpoint")
	}
	if !exists {
		t.Error("exists should be true for existing endpoint")
	}

	// Test non-existing endpoint
	slug, exists = app.CheckEndpointExists("New Endpoint")
	if slug != "new-endpoint" {
		t.Errorf("slug = %q, want %q", slug, "new-endpoint")
	}
	if exists {
		t.Error("exists should be false for non-existing endpoint")
	}
}

func TestCheckEndpointExistsNotConfigured(t *testing.T) {
	app := &App{}
	slug, exists := app.CheckEndpointExists("Test")
	if slug != "" {
		t.Errorf("slug should be empty when not configured, got %q", slug)
	}
	if exists {
		t.Error("exists should be false when not configured")
	}
}

func TestCheckEndpointExistsEmptyName(t *testing.T) {
	tempDir := t.TempDir()
	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	slug, exists := app.CheckEndpointExists("")
	if slug != "" {
		t.Errorf("slug should be empty for empty name, got %q", slug)
	}
	if exists {
		t.Error("exists should be false for empty name")
	}
}

func TestListPolicyFiles(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	policyDir := filepath.Join(endpointDir, "policy")
	if err := os.MkdirAll(policyDir, 0755); err != nil {
		t.Fatalf("Failed to create policy dir: %v", err)
	}

	// Create policy file
	policyContent := `name: rate-limit
type: RateLimitPolicy
config:
  max_requests: 100
`
	policyPath := filepath.Join(policyDir, "rate-limit.yaml")
	if err := os.WriteFile(policyPath, []byte(policyContent), 0644); err != nil {
		t.Fatalf("Failed to write policy file: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	policies, err := app.ListPolicyFiles("test-endpoint")
	if err != nil {
		t.Fatalf("ListPolicyFiles error: %v", err)
	}
	if len(policies) != 1 {
		t.Errorf("Expected 1 policy file, got %d", len(policies))
	}
	if policies[0].Filename != "rate-limit.yaml" {
		t.Errorf("Filename = %q, want %q", policies[0].Filename, "rate-limit.yaml")
	}
	if policies[0].Name != "rate-limit" {
		t.Errorf("Name = %q, want %q", policies[0].Name, "rate-limit")
	}
	if policies[0].Type != "RateLimitPolicy" {
		t.Errorf("Type = %q, want %q", policies[0].Type, "RateLimitPolicy")
	}
}

func TestListPolicyFilesNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.ListPolicyFiles("test-endpoint")
	if err == nil {
		t.Error("ListPolicyFiles should error when not configured")
	}
}

func TestListPolicyFilesNoPolicyDir(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		t.Fatalf("Failed to create endpoint dir: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	// Should return empty slice for missing policy directory
	policies, err := app.ListPolicyFiles("test-endpoint")
	if err != nil {
		t.Fatalf("ListPolicyFiles should not error for missing dir: %v", err)
	}
	if len(policies) != 0 {
		t.Errorf("Expected empty slice, got %d items", len(policies))
	}
}

func TestGetPolicyFileYaml(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	policyDir := filepath.Join(endpointDir, "policy")
	if err := os.MkdirAll(policyDir, 0755); err != nil {
		t.Fatalf("Failed to create policy dir: %v", err)
	}

	policyContent := `name: rate-limit
type: RateLimitPolicy
`
	policyPath := filepath.Join(policyDir, "rate-limit.yaml")
	if err := os.WriteFile(policyPath, []byte(policyContent), 0644); err != nil {
		t.Fatalf("Failed to write policy file: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	content, err := app.GetPolicyFileYaml("test-endpoint", "rate-limit.yaml")
	if err != nil {
		t.Fatalf("GetPolicyFileYaml error: %v", err)
	}
	if content != policyContent {
		t.Errorf("GetPolicyFileYaml returned wrong content")
	}
}

func TestGetPolicyFileYamlNotConfigured(t *testing.T) {
	app := &App{}
	_, err := app.GetPolicyFileYaml("test-endpoint", "test.yaml")
	if err == nil {
		t.Error("GetPolicyFileYaml should error when not configured")
	}
}

func TestGetPolicyFileYamlEmptyFilename(t *testing.T) {
	tempDir := t.TempDir()
	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	_, err := app.GetPolicyFileYaml("test-endpoint", "")
	if err == nil {
		t.Error("GetPolicyFileYaml should error for empty filename")
	}
}

func TestGetPolicyFileYamlPathTraversal(t *testing.T) {
	tempDir := t.TempDir()
	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	// Test path traversal attempts
	testCases := []string{
		"../secret.yaml",
		"..\\secret.yaml",
		"subdir/file.yaml",
		"subdir\\file.yaml",
	}

	for _, filename := range testCases {
		_, err := app.GetPolicyFileYaml("test-endpoint", filename)
		if err == nil {
			t.Errorf("GetPolicyFileYaml should error for path traversal: %q", filename)
		}
	}
}

func TestGetPolicyFileYamlNotFound(t *testing.T) {
	tempDir := t.TempDir()
	endpointDir := filepath.Join(tempDir, "test-endpoint")
	policyDir := filepath.Join(endpointDir, "policy")
	if err := os.MkdirAll(policyDir, 0755); err != nil {
		t.Fatalf("Failed to create policy dir: %v", err)
	}

	app := &App{
		config: &app.Config{
			EndpointsPath: tempDir,
		},
	}

	_, err := app.GetPolicyFileYaml("test-endpoint", "nonexistent.yaml")
	if err == nil {
		t.Error("GetPolicyFileYaml should error for nonexistent file")
	}
}
