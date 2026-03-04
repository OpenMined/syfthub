package nodeops

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Manager provides endpoint file operations scoped to an endpoints directory.
type Manager struct {
	EndpointsPath string
}

// NewManager creates a new Manager for the given endpoints directory.
func NewManager(endpointsPath string) *Manager {
	return &Manager{EndpointsPath: endpointsPath}
}

// CreateEndpoint scaffolds a new endpoint directory with runner.py, pyproject.toml, and README.md.
// Returns the generated slug.
func (m *Manager) CreateEndpoint(req CreateEndpointRequest) (string, error) {
	if req.Name == "" {
		return "", fmt.Errorf("endpoint name is required")
	}
	if req.Type != "model" && req.Type != "data_source" {
		return "", fmt.Errorf("endpoint type must be 'model' or 'data_source'")
	}

	slug := Slugify(req.Name)
	if slug == "" {
		return "", fmt.Errorf("could not generate valid slug from name '%s'", req.Name)
	}

	endpointDir := filepath.Join(m.EndpointsPath, slug)
	if _, err := os.Stat(endpointDir); !os.IsNotExist(err) {
		return "", fmt.Errorf("endpoint '%s' already exists", slug)
	}

	if err := os.MkdirAll(endpointDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create endpoint directory: %w", err)
	}

	cleanup := func() {
		os.RemoveAll(endpointDir)
	}

	// Create runner.py
	runnerContent := GetRunnerTemplate(req.Type)
	runnerPath := filepath.Join(endpointDir, "runner.py")
	if err := os.WriteFile(runnerPath, []byte(runnerContent), 0644); err != nil {
		cleanup()
		return "", fmt.Errorf("failed to create runner.py: %w", err)
	}

	// Create pyproject.toml
	version := req.Version
	if version == "" {
		version = "1.0.0"
	}
	pyprojectContent := fmt.Sprintf("[project]\nname = \"%s\"\nversion = \"%s\"\ndependencies = []\n", slug, version)
	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	if err := os.WriteFile(pyprojectPath, []byte(pyprojectContent), 0644); err != nil {
		cleanup()
		return "", fmt.Errorf("failed to create pyproject.toml: %w", err)
	}

	// Create README.md with YAML frontmatter
	description := req.Description
	if description == "" {
		description = fmt.Sprintf("A %s endpoint", req.Type)
	}
	enabled := true
	fm := &ReadmeFrontmatter{
		Slug:        slug,
		Type:        req.Type,
		Name:        req.Name,
		Description: description,
		Version:     version,
		Enabled:     &enabled,
	}
	body := fmt.Sprintf("# %s\n\n%s\n\n## Usage\n\nEdit the runner.py file to implement your endpoint logic.", req.Name, description)
	readmePath := filepath.Join(endpointDir, "README.md")
	if err := WriteReadmeWithFrontmatter(readmePath, fm, body); err != nil {
		cleanup()
		return "", fmt.Errorf("failed to create README.md: %w", err)
	}

	return slug, nil
}

// DeleteEndpoint removes an endpoint directory and all its contents.
func (m *Manager) DeleteEndpoint(slug string) error {
	if slug == "" {
		return fmt.Errorf("endpoint slug is required")
	}
	if strings.Contains(slug, "..") || strings.Contains(slug, "/") || strings.Contains(slug, "\\") {
		return fmt.Errorf("invalid endpoint slug")
	}

	endpointDir := filepath.Join(m.EndpointsPath, slug)
	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		return fmt.Errorf("endpoint not found: %s", slug)
	}

	if err := os.RemoveAll(endpointDir); err != nil {
		return fmt.Errorf("failed to delete endpoint: %w", err)
	}

	return nil
}

// ListEndpoints lists all endpoints in the endpoints directory with basic info.
func (m *Manager) ListEndpoints() ([]EndpointInfo, error) {
	entries, err := os.ReadDir(m.EndpointsPath)
	if err != nil {
		if os.IsNotExist(err) {
			return []EndpointInfo{}, nil
		}
		return nil, fmt.Errorf("failed to read endpoints directory: %w", err)
	}

	var endpoints []EndpointInfo
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		name := entry.Name()
		// Skip hidden and special directories
		if strings.HasPrefix(name, ".") || strings.HasPrefix(name, "__") {
			continue
		}

		info := EndpointInfo{
			Slug:    name,
			Name:    name,
			Type:    "model",
			Version: "1.0.0",
			Enabled: true,
		}

		readmePath := filepath.Join(m.EndpointsPath, name, "README.md")
		if fm, _, err := ParseReadmeFrontmatter(readmePath); err == nil {
			if fm.Name != "" {
				info.Name = fm.Name
			}
			if fm.Description != "" {
				info.Description = fm.Description
			}
			if fm.Type != "" {
				info.Type = fm.Type
			}
			if fm.Version != "" {
				info.Version = fm.Version
			}
			if fm.Enabled != nil {
				info.Enabled = *fm.Enabled
			}
		}

		policiesPath := filepath.Join(m.EndpointsPath, name, "policies.yaml")
		if _, err := os.Stat(policiesPath); err == nil {
			info.HasPolicies = true
		}

		pyprojectPath := filepath.Join(m.EndpointsPath, name, "pyproject.toml")
		if deps, err := ReadDependencies(pyprojectPath); err == nil {
			info.DepsCount = len(deps)
		}

		envPath := filepath.Join(m.EndpointsPath, name, ".env")
		if envVars, err := ReadEnvFile(envPath); err == nil {
			info.EnvCount = len(envVars)
		}

		endpoints = append(endpoints, info)
	}

	return endpoints, nil
}

// GetEndpointDetail returns full details for an endpoint.
func (m *Manager) GetEndpointDetail(slug string) (*EndpointDetail, error) {
	endpointDir := filepath.Join(m.EndpointsPath, slug)
	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		return nil, fmt.Errorf("endpoint not found: %s", slug)
	}

	detail := &EndpointDetail{
		Slug:    slug,
		Name:    slug,
		Type:    "model",
		Version: "1.0.0",
		Enabled: true,
	}

	readmePath := filepath.Join(endpointDir, "README.md")
	if _, err := os.Stat(readmePath); err == nil {
		detail.HasReadme = true
		if content, err := os.ReadFile(readmePath); err == nil {
			detail.ReadmeContent = string(content)
		}
		if fm, _, err := ParseReadmeFrontmatter(readmePath); err == nil {
			if fm.Name != "" {
				detail.Name = fm.Name
			}
			if fm.Slug != "" {
				detail.Slug = fm.Slug
			}
			if fm.Description != "" {
				detail.Description = fm.Description
			}
			if fm.Type != "" {
				detail.Type = fm.Type
			}
			if fm.Version != "" {
				detail.Version = fm.Version
			}
			if fm.Enabled != nil {
				detail.Enabled = *fm.Enabled
			}
		}
	}

	runnerPath := filepath.Join(endpointDir, "runner.py")
	if content, err := os.ReadFile(runnerPath); err == nil {
		detail.RunnerCode = string(content)
	}

	policiesPath := filepath.Join(endpointDir, "policies.yaml")
	if policies, version, err := ParsePoliciesYaml(policiesPath); err == nil {
		detail.HasPolicies = true
		detail.Policies = policies
		detail.PoliciesVersion = version
	}

	envPath := filepath.Join(endpointDir, ".env")
	if envVars, err := ReadEnvFile(envPath); err == nil {
		detail.EnvCount = len(envVars)
	}

	pyprojectPath := filepath.Join(endpointDir, "pyproject.toml")
	if deps, err := ReadDependencies(pyprojectPath); err == nil {
		detail.DepsCount = len(deps)
	}

	return detail, nil
}

// GetRunnerTemplate returns the Python runner.py template for the given endpoint type.
func GetRunnerTemplate(endpointType string) string {
	if endpointType == "model" {
		return `"""
Model endpoint handler.

This handler processes incoming requests to your model endpoint.
"""


def handler(messages: list, context: dict = None) -> str:
    """
    Echo back the last user message.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        context: Optional context metadata

    Returns:
        The echoed message
    """
    # Find the last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return f"Echo: {content}"
    return "Hello world!"
`
	}

	return `"""
Data Source Endpoint Runner

This endpoint provides access to data sources (databases, APIs, files).
Implement the handler() function to handle data requests.
"""


def handler(query: str, context: dict = None) -> list[dict]:
    """
    Query data from your data source.

    Args:
        query: The search query string
        context: Optional context metadata

    Returns:
        List of document dicts, each with keys:
            - document_id (str): Unique identifier for the document
            - content (str): The document text content
            - metadata (dict): Additional metadata (title, source, etc.)
            - similarity_score (float): Relevance score between 0.0 and 1.0
    """
    # TODO: Implement your data source logic here
    # Example: Execute SQL, call external API, search a vector store, etc.

    return [
        {
            "document_id": "doc-001",
            "content": "Example document content matching the query.",
            "metadata": {"title": "Example Document", "source": "example"},
            "similarity_score": 1.0,
        }
    ]
`
}
