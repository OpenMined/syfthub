package connectors

import (
	"embed"
	"fmt"
	"sort"

	"gopkg.in/yaml.v3"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

//go:embed *.yaml
var embeddedConnectors embed.FS

// Registry provides access to built-in connector templates.
type Registry struct {
	templates map[string]*ConnectorTemplate
}

// ConnectorTemplate is a parsed connector template.
type ConnectorTemplate struct {
	Meta      ConnectorMeta           `yaml:"meta"`
	Params    map[string]ParamDef     `yaml:"params,omitempty"`
	Steps     []nodeops.SetupStep     `yaml:"steps"`
	Lifecycle *nodeops.SetupLifecycle `yaml:"lifecycle,omitempty"`
}

// ConnectorMeta contains metadata about a connector template.
type ConnectorMeta struct {
	ID          string   `yaml:"id"`
	Name        string   `yaml:"name"`
	Description string   `yaml:"description"`
	Category    string   `yaml:"category"`
	Tags        []string `yaml:"tags"`
}

// ParamDef defines a parameter that can be overridden when scaffolding.
type ParamDef struct {
	Default     interface{} `yaml:"default"`
	Description string      `yaml:"description"`
}

// NewRegistry loads all embedded connector templates.
func NewRegistry() *Registry {
	r := &Registry{
		templates: make(map[string]*ConnectorTemplate),
	}

	entries, err := embeddedConnectors.ReadDir(".")
	if err != nil {
		return r
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		// Skip non-YAML files (like this .go file won't be embedded anyway)
		if len(name) < 5 || name[len(name)-5:] != ".yaml" {
			continue
		}

		data, err := embeddedConnectors.ReadFile(name)
		if err != nil {
			continue
		}

		var tmpl ConnectorTemplate
		if err := yaml.Unmarshal(data, &tmpl); err != nil {
			continue
		}

		if tmpl.Meta.ID != "" {
			r.templates[tmpl.Meta.ID] = &tmpl
		}
	}

	return r
}

// List returns all available connector templates, sorted by ID.
func (r *Registry) List() []ConnectorMeta {
	var metas []ConnectorMeta
	for _, tmpl := range r.templates {
		metas = append(metas, tmpl.Meta)
	}
	sort.Slice(metas, func(i, j int) bool {
		return metas[i].ID < metas[j].ID
	})
	return metas
}

// Get returns a connector template by ID.
func (r *Registry) Get(id string) (*ConnectorTemplate, error) {
	tmpl, ok := r.templates[id]
	if !ok {
		return nil, fmt.Errorf("connector template '%s' not found", id)
	}
	return tmpl, nil
}

// Scaffold merges one or more connector templates into a setup.yaml spec.
// Handles:
//   - Deduplicating step IDs (prefix with connector ID if conflict)
//   - Merging lifecycle configs
func (r *Registry) Scaffold(connectorIDs []string, params map[string]map[string]interface{}) (*nodeops.SetupSpec, error) {
	if len(connectorIDs) == 0 {
		return nil, fmt.Errorf("at least one connector ID is required")
	}

	spec := &nodeops.SetupSpec{
		Version: "1",
	}

	usedStepIDs := make(map[string]bool)
	var refreshSteps []string

	for _, connID := range connectorIDs {
		tmpl, err := r.Get(connID)
		if err != nil {
			return nil, err
		}

		// Determine prefix for step IDs if there are conflicts
		prefix := ""
		if len(connectorIDs) > 1 {
			// Check for potential conflicts
			for _, step := range tmpl.Steps {
				if usedStepIDs[step.ID] {
					prefix = connID + "_"
					break
				}
			}
		}

		// Add steps with optional prefix
		for _, step := range tmpl.Steps {
			stepCopy := step
			if prefix != "" {
				stepCopy.ID = prefix + step.ID

				// Update depends_on references
				if len(stepCopy.DependsOn) > 0 {
					newDeps := make([]string, len(stepCopy.DependsOn))
					for i, dep := range stepCopy.DependsOn {
						if usedStepIDs[dep] {
							// Dependency is from a previous connector, keep as-is
							newDeps[i] = dep
						} else {
							newDeps[i] = prefix + dep
						}
					}
					stepCopy.DependsOn = newDeps
				}

				// Update options_from step_id reference
				if stepCopy.Select != nil && stepCopy.Select.OptionsFrom != nil {
					if !usedStepIDs[stepCopy.Select.OptionsFrom.StepID] {
						stepCopy.Select.OptionsFrom.StepID = prefix + stepCopy.Select.OptionsFrom.StepID
					}
				}
			}

			usedStepIDs[stepCopy.ID] = true
			spec.Steps = append(spec.Steps, stepCopy)
		}

		// Merge lifecycle
		if tmpl.Lifecycle != nil && tmpl.Lifecycle.Refresh != nil {
			for _, stepID := range tmpl.Lifecycle.Refresh.Steps {
				actualID := stepID
				if prefix != "" {
					actualID = prefix + stepID
				}
				refreshSteps = append(refreshSteps, actualID)
			}
		}
	}

	// Build merged lifecycle if any refresh steps exist
	if len(refreshSteps) > 0 {
		spec.Lifecycle = &nodeops.SetupLifecycle{
			Refresh: &nodeops.LifecycleRefresh{
				Trigger:  "token_expiry",
				Steps:    refreshSteps,
				Strategy: "refresh_token",
			},
		}
	}

	return spec, nil
}
