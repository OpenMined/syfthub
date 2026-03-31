package nodeops

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// ParsePoliciesYaml parses a policies.yaml file and returns the policies list.
func ParsePoliciesYaml(path string) ([]Policy, string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, "", err
	}

	var pf PoliciesFile
	if err := yaml.Unmarshal(content, &pf); err != nil {
		return nil, "", fmt.Errorf("failed to parse policies.yaml: %w", err)
	}

	return pf.Policies, pf.Version, nil
}

// GetPolicies returns policies for an endpoint, returning an empty slice if
// the file doesn't exist.
func GetPolicies(policiesPath string) ([]Policy, error) {
	policies, _, err := ParsePoliciesYaml(policiesPath)
	if err != nil {
		if os.IsNotExist(err) {
			return []Policy{}, nil
		}
		return nil, err
	}
	return policies, nil
}

// SavePolicy creates or updates a policy by name in policies.yaml.
// Creates the default structure if the file doesn't exist.
func SavePolicy(policiesPath string, policy Policy) error {
	if policy.Name == "" {
		return fmt.Errorf("policy name is required")
	}
	if policy.Type == "" {
		return fmt.Errorf("policy type is required")
	}

	var pf PoliciesFile
	if content, err := os.ReadFile(policiesPath); err == nil {
		if err := yaml.Unmarshal(content, &pf); err != nil {
			return fmt.Errorf("failed to parse policies.yaml: %w", err)
		}
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("failed to read policies.yaml: %w", err)
	} else {
		pf = PoliciesFile{
			Version: "1.0",
			Store: map[string]interface{}{
				"type": "sqlite",
				"path": ".policy_store.db",
			},
			Policies: []Policy{},
		}
	}

	found := false
	for i, p := range pf.Policies {
		if p.Name == policy.Name {
			pf.Policies[i] = policy
			found = true
			break
		}
	}
	if !found {
		pf.Policies = append(pf.Policies, policy)
	}

	content, err := yaml.Marshal(&pf)
	if err != nil {
		return fmt.Errorf("failed to marshal policies: %w", err)
	}

	return os.WriteFile(policiesPath, content, 0644)
}

// DeletePolicy removes a policy by name from policies.yaml.
func DeletePolicy(policiesPath string, policyName string) error {
	if policyName == "" {
		return fmt.Errorf("policy name is required")
	}

	content, err := os.ReadFile(policiesPath)
	if err != nil {
		return fmt.Errorf("failed to read policies.yaml: %w", err)
	}

	var pf PoliciesFile
	if err := yaml.Unmarshal(content, &pf); err != nil {
		return fmt.Errorf("failed to parse policies.yaml: %w", err)
	}

	found := false
	var newPolicies []Policy
	for _, p := range pf.Policies {
		if p.Name == policyName {
			found = true
			continue
		}
		newPolicies = append(newPolicies, p)
	}

	if !found {
		return fmt.Errorf("policy not found: %s", policyName)
	}

	pf.Policies = newPolicies

	newContent, err := yaml.Marshal(&pf)
	if err != nil {
		return fmt.Errorf("failed to marshal policies: %w", err)
	}

	return os.WriteFile(policiesPath, newContent, 0644)
}
