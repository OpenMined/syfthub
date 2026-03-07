package nodeops

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"time"

	"gopkg.in/yaml.v3"
)

// ParseSetupYaml reads and parses a setup.yaml file.
// Returns nil (not error) if the file does not exist.
func ParseSetupYaml(path string) (*SetupSpec, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to read setup.yaml: %w", err)
	}

	var spec SetupSpec
	if err := yaml.Unmarshal(content, &spec); err != nil {
		return nil, fmt.Errorf("failed to parse setup.yaml: %w", err)
	}

	return &spec, nil
}

// WriteSetupYaml writes a SetupSpec to a setup.yaml file.
func WriteSetupYaml(path string, spec *SetupSpec) error {
	data, err := yaml.Marshal(spec)
	if err != nil {
		return fmt.Errorf("failed to marshal setup.yaml: %w", err)
	}
	return os.WriteFile(path, data, 0644)
}

// ValidateSetupSpec checks the spec for structural correctness:
//   - All step IDs are unique
//   - All depends_on references exist
//   - No dependency cycles (topological sort)
//   - Each step has exactly one type-specific config matching its type
//   - Required fields per type
func ValidateSetupSpec(spec *SetupSpec) error {
	if spec == nil {
		return fmt.Errorf("setup spec is nil")
	}

	validTypes := map[string]bool{
		StepTypePrompt:   true,
		StepTypeSelect:   true,
		StepTypeOAuth2:   true,
		StepTypeHTTP:     true,
		StepTypeTemplate: true,
		StepTypeExec:     true,
	}

	// 1. Collect all step IDs; check for duplicates
	stepIDs := make(map[string]bool)
	for _, step := range spec.Steps {
		if step.ID == "" {
			return fmt.Errorf("step missing required field: id")
		}
		if stepIDs[step.ID] {
			return fmt.Errorf("duplicate step ID: %s", step.ID)
		}
		stepIDs[step.ID] = true
	}

	// 2. Validate each step
	for _, step := range spec.Steps {
		// Verify type is valid
		if !validTypes[step.Type] {
			return fmt.Errorf("step '%s': unknown type '%s'", step.ID, step.Type)
		}

		// Verify matching type-specific config is non-nil
		switch step.Type {
		case StepTypePrompt:
			if step.Prompt == nil {
				return fmt.Errorf("step '%s': type 'prompt' requires prompt config", step.ID)
			}
			if step.Prompt.Message == "" {
				return fmt.Errorf("step '%s': prompt.message is required", step.ID)
			}
			// Validate regex pattern if present
			if step.Prompt.Validate != nil && step.Prompt.Validate.Pattern != "" {
				if _, err := regexp.Compile(step.Prompt.Validate.Pattern); err != nil {
					return fmt.Errorf("step '%s': invalid validate.pattern: %w", step.ID, err)
				}
			}
		case StepTypeSelect:
			if step.Select == nil {
				return fmt.Errorf("step '%s': type 'select' requires select config", step.ID)
			}
			if len(step.Select.Options) == 0 && step.Select.OptionsFrom == nil {
				return fmt.Errorf("step '%s': select requires options or options_from", step.ID)
			}
		case StepTypeOAuth2:
			if step.OAuth2 == nil {
				return fmt.Errorf("step '%s': type 'oauth2' requires oauth2 config", step.ID)
			}
			if step.OAuth2.AuthURL == "" {
				return fmt.Errorf("step '%s': oauth2.auth_url is required", step.ID)
			}
			if step.OAuth2.TokenURL == "" {
				return fmt.Errorf("step '%s': oauth2.token_url is required", step.ID)
			}
		case StepTypeHTTP:
			if step.HTTP == nil {
				return fmt.Errorf("step '%s': type 'http' requires http config", step.ID)
			}
			if step.HTTP.Method == "" {
				return fmt.Errorf("step '%s': http.method is required", step.ID)
			}
			if step.HTTP.URL == "" {
				return fmt.Errorf("step '%s': http.url is required", step.ID)
			}
		case StepTypeTemplate:
			if step.Template == nil {
				return fmt.Errorf("step '%s': type 'template' requires template config", step.ID)
			}
			if step.Template.Value == "" {
				return fmt.Errorf("step '%s': template.value is required", step.ID)
			}
		case StepTypeExec:
			if step.Exec == nil {
				return fmt.Errorf("step '%s': type 'exec' requires exec config", step.ID)
			}
			if step.Exec.Command == "" {
				return fmt.Errorf("step '%s': exec.command is required", step.ID)
			}
		}

		// Verify depends_on references exist
		for _, dep := range step.DependsOn {
			if !stepIDs[dep] {
				return fmt.Errorf("step '%s': depends_on references nonexistent step '%s'", step.ID, dep)
			}
		}
	}

	// 3. Run topological sort to detect cycles
	if _, err := TopologicalSort(spec.Steps); err != nil {
		return err
	}

	// 4. If lifecycle refresh steps set, verify all referenced IDs exist
	if spec.Lifecycle != nil && spec.Lifecycle.Refresh != nil {
		for _, stepID := range spec.Lifecycle.Refresh.Steps {
			if !stepIDs[stepID] {
				return fmt.Errorf("lifecycle.refresh references nonexistent step '%s'", stepID)
			}
		}
	}

	return nil
}

// TopologicalSort returns step IDs in dependency-respecting execution order.
// Uses Kahn's algorithm. Returns error if the graph has cycles.
func TopologicalSort(steps []SetupStep) ([]string, error) {
	// Build adjacency list and in-degree map
	inDegree := make(map[string]int)
	dependents := make(map[string][]string) // step -> list of steps that depend on it
	stepOrder := make([]string, 0, len(steps))

	for _, step := range steps {
		stepOrder = append(stepOrder, step.ID)
		if _, ok := inDegree[step.ID]; !ok {
			inDegree[step.ID] = 0
		}
		for _, dep := range step.DependsOn {
			inDegree[step.ID]++
			dependents[dep] = append(dependents[dep], step.ID)
		}
	}

	// Initialize queue with all steps having in-degree 0
	// Use a slice as queue, maintaining original order for determinism
	var queue []string
	for _, id := range stepOrder {
		if inDegree[id] == 0 {
			queue = append(queue, id)
		}
	}

	var result []string
	for len(queue) > 0 {
		// Dequeue
		current := queue[0]
		queue = queue[1:]
		result = append(result, current)

		// For each dependent, decrement in-degree
		for _, dep := range dependents[current] {
			inDegree[dep]--
			if inDegree[dep] == 0 {
				queue = append(queue, dep)
			}
		}
	}

	if len(result) != len(steps) {
		return nil, fmt.Errorf("dependency cycle detected in setup steps")
	}

	return result, nil
}

// ReadSetupState reads .setup-state.json from the endpoint directory.
// Returns empty state (not error) if the file does not exist.
func ReadSetupState(dir string) (*SetupState, error) {
	path := filepath.Join(dir, ".setup-state.json")
	content, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return &SetupState{
				Version: "1",
				Steps:   make(map[string]StepState),
			}, nil
		}
		return nil, fmt.Errorf("failed to read .setup-state.json: %w", err)
	}

	var state SetupState
	if err := json.Unmarshal(content, &state); err != nil {
		return nil, fmt.Errorf("failed to parse .setup-state.json: %w", err)
	}
	if state.Steps == nil {
		state.Steps = make(map[string]StepState)
	}

	return &state, nil
}

// WriteSetupState writes .setup-state.json to the endpoint directory.
func WriteSetupState(dir string, state *SetupState) error {
	path := filepath.Join(dir, ".setup-state.json")
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal .setup-state.json: %w", err)
	}
	return os.WriteFile(path, data, 0600)
}

// GetSetupStatus computes the setup status by comparing spec against state.
// Returns a status indicating has_setup=false if no setup.yaml exists.
func GetSetupStatus(dir string) (*SetupStatus, error) {
	setupPath := filepath.Join(dir, "setup.yaml")
	spec, err := ParseSetupYaml(setupPath)
	if err != nil {
		return nil, err
	}
	if spec == nil {
		return &SetupStatus{HasSetup: false, IsComplete: true}, nil
	}

	state, err := ReadSetupState(dir)
	if err != nil {
		return nil, err
	}

	status := &SetupStatus{
		HasSetup:   true,
		TotalSteps: len(spec.Steps),
	}

	for _, step := range spec.Steps {
		ss, exists := state.Steps[step.ID]
		if exists && ss.Status == StepStatusCompleted {
			// Check expiry
			if ss.ExpiresAt != "" {
				expiresAt, err := time.Parse(time.RFC3339, ss.ExpiresAt)
				if err == nil && time.Now().After(expiresAt) {
					status.ExpiredSteps = append(status.ExpiredSteps, step.ID)
					continue
				}
			}
			status.CompletedN++
		} else if step.Required {
			status.PendingSteps = append(status.PendingSteps, step.ID)
		} else {
			// Optional step not done — still counts towards total but not pending
		}
	}

	status.IsComplete = len(status.PendingSteps) == 0 && len(status.ExpiredSteps) == 0

	return status, nil
}

// HasSetup returns true if setup.yaml exists in the directory.
func HasSetup(dir string) bool {
	setupPath := filepath.Join(dir, "setup.yaml")
	_, err := os.Stat(setupPath)
	return err == nil
}
