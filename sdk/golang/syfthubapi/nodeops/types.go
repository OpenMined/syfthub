// Package nodeops provides shared file-I/O operations for managing SyftHub
// endpoint directories. It is consumed by both the CLI and the desktop app.
// This package has zero Wails or syfthubapi dependencies.
package nodeops

// ReadmeFrontmatter represents the YAML frontmatter in an endpoint's README.md.
type ReadmeFrontmatter struct {
	Slug        string `yaml:"slug" json:"slug"`
	Name        string `yaml:"name" json:"name"`
	Description string `yaml:"description" json:"description"`
	Type        string `yaml:"type" json:"type"`
	Version     string `yaml:"version" json:"version"`
	Enabled     *bool  `yaml:"enabled" json:"enabled"`
}

// Policy represents a single policy from policies.yaml.
type Policy struct {
	Name   string                 `json:"name" yaml:"name"`
	Type   string                 `json:"type" yaml:"type"`
	Config map[string]interface{} `json:"config" yaml:"config"`
}

// PoliciesFile represents the full policies.yaml structure.
type PoliciesFile struct {
	Version  string                 `yaml:"version"`
	Store    map[string]interface{} `yaml:"store"`
	Policies []Policy               `yaml:"policies"`
}

// EnvVar represents an environment variable key-value pair.
type EnvVar struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

// Dependency represents a Python package dependency.
type Dependency struct {
	Package string `json:"package"`
	Version string `json:"version"`
}

// CreateEndpointRequest contains the parameters for creating a new endpoint.
type CreateEndpointRequest struct {
	Name        string `json:"name"`
	Type        string `json:"type"`
	Description string `json:"description"`
	Version     string `json:"version"`
}

// EndpointInfo represents an endpoint for display purposes.
type EndpointInfo struct {
	Slug        string `json:"slug"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Type        string `json:"type"`
	Version     string `json:"version"`
	Enabled     bool   `json:"enabled"`
	HasPolicies bool   `json:"hasPolicies"`
	DepsCount   int    `json:"depsCount"`
	EnvCount    int    `json:"envCount"`
}

// EndpointDetail provides full endpoint information including file contents.
type EndpointDetail struct {
	Slug            string   `json:"slug"`
	Name            string   `json:"name"`
	Description     string   `json:"description"`
	Type            string   `json:"type"`
	Version         string   `json:"version"`
	Enabled         bool     `json:"enabled"`
	HasReadme       bool     `json:"hasReadme"`
	HasPolicies     bool     `json:"hasPolicies"`
	DepsCount       int      `json:"depsCount"`
	EnvCount        int      `json:"envCount"`
	RunnerCode      string   `json:"runnerCode"`
	ReadmeContent   string   `json:"readmeContent"`
	Policies        []Policy `json:"policies"`
	PoliciesVersion string   `json:"policiesVersion"`
}

// PackageConfigField describes a configuration field for a marketplace package.
type PackageConfigField struct {
	Key         string `json:"key"`
	Label       string `json:"label"`
	Description string `json:"description,omitempty"`
	Required    bool   `json:"required"`
	Secret      bool   `json:"secret"`
	Default     string `json:"default,omitempty"`
}

// MarketplacePackage represents an installable endpoint package from the marketplace.
type MarketplacePackage struct {
	Slug        string               `json:"slug"`
	Name        string               `json:"name"`
	Description string               `json:"description"`
	Type        string               `json:"type"`
	Author      string               `json:"author,omitempty"`
	Version     string               `json:"version"`
	DownloadURL string               `json:"downloadUrl"`
	Tags        []string             `json:"tags,omitempty"`
	Config      []PackageConfigField `json:"config,omitempty"`
}

// MarketplaceManifest is the top-level structure of the marketplace JSON file.
type MarketplaceManifest struct {
	Packages []MarketplacePackage `json:"packages"`
}
