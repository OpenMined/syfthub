package nodeops

import (
	"os"
	"path/filepath"
	"testing"
)

func TestSavePolicy(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policies.yaml")

	policy := Policy{
		Name:   "rate-limit",
		Type:   "RateLimitPolicy",
		Config: map[string]interface{}{"max_requests": 100},
	}

	if err := SavePolicy(path, policy); err != nil {
		t.Fatal(err)
	}

	policies, err := GetPolicies(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(policies) != 1 {
		t.Fatalf("expected 1 policy, got %d", len(policies))
	}
	if policies[0].Name != "rate-limit" {
		t.Errorf("policy name = %q, want %q", policies[0].Name, "rate-limit")
	}
}

func TestSavePolicy_Update(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policies.yaml")

	// Add initial policy
	SavePolicy(path, Policy{Name: "p1", Type: "TypeA", Config: map[string]interface{}{"x": 1}})

	// Update same policy
	SavePolicy(path, Policy{Name: "p1", Type: "TypeB", Config: map[string]interface{}{"x": 2}})

	policies, _ := GetPolicies(path)
	if len(policies) != 1 {
		t.Fatalf("expected 1 policy after update, got %d", len(policies))
	}
	if policies[0].Type != "TypeB" {
		t.Errorf("policy type = %q, want %q", policies[0].Type, "TypeB")
	}
}

func TestDeletePolicy(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policies.yaml")

	SavePolicy(path, Policy{Name: "keep", Type: "A"})
	SavePolicy(path, Policy{Name: "remove", Type: "B"})

	if err := DeletePolicy(path, "remove"); err != nil {
		t.Fatal(err)
	}

	policies, _ := GetPolicies(path)
	if len(policies) != 1 {
		t.Fatalf("expected 1 policy, got %d", len(policies))
	}
	if policies[0].Name != "keep" {
		t.Errorf("remaining policy = %q, want %q", policies[0].Name, "keep")
	}
}

func TestDeletePolicy_NotFound(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policies.yaml")

	SavePolicy(path, Policy{Name: "exists", Type: "A"})

	err := DeletePolicy(path, "nonexistent")
	if err == nil {
		t.Error("expected error for nonexistent policy")
	}
}

func TestGetPolicies_NoFile(t *testing.T) {
	policies, err := GetPolicies("/nonexistent/policies.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if len(policies) != 0 {
		t.Errorf("expected 0 policies, got %d", len(policies))
	}
}

func TestParsePoliciesYaml(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "policies.yaml")

	content := `version: "1.0"
store:
  type: sqlite
  path: .policy_store.db
policies:
  - name: test-policy
    type: RateLimitPolicy
    config:
      max_requests: 50
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	policies, version, err := ParsePoliciesYaml(path)
	if err != nil {
		t.Fatal(err)
	}
	if version != "1.0" {
		t.Errorf("version = %q, want %q", version, "1.0")
	}
	if len(policies) != 1 {
		t.Fatalf("expected 1 policy, got %d", len(policies))
	}
	if policies[0].Name != "test-policy" {
		t.Errorf("policy name = %q, want %q", policies[0].Name, "test-policy")
	}
}
