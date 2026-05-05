package main

import "time"

// PackageType constrains endpoint package types.
type PackageType string

const (
	PackageTypeModel      PackageType = "model"
	PackageTypeDataSource PackageType = "data_source"
	PackageTypeAgent      PackageType = "agent"
)

func (t PackageType) Valid() bool {
	return t == PackageTypeModel || t == PackageTypeDataSource || t == PackageTypeAgent
}

// PackageConfigField describes a configuration field for package installation.
// Matches syfthub-desktop/types.go:219-228 exactly.
type PackageConfigField struct {
	Key         string `json:"key"`
	Label       string `json:"label"`
	Description string `json:"description,omitempty"`
	Required    bool   `json:"required"`
	Secret      bool   `json:"secret"`
	Default     string `json:"default,omitempty"`
}

// Package is the full internal representation stored in SQLite.
type Package struct {
	ID          int64              `json:"id"`
	Slug        string             `json:"slug"`
	Name        string             `json:"name"`
	Description string             `json:"description"`
	Type        PackageType        `json:"type"`
	Author      string             `json:"author,omitempty"`
	Version     string             `json:"version"`
	DownloadURL string             `json:"downloadUrl,omitempty"`
	Tags        []string           `json:"tags,omitempty"`
	Config      []PackageConfigField `json:"config,omitempty"`
	ZipSize     int64              `json:"zipSize,omitempty"`
	ZipSHA256   string             `json:"zipSha256,omitempty"`
	CreatedAt   time.Time          `json:"createdAt"`
	UpdatedAt   time.Time          `json:"updatedAt"`
}

// ManifestPackage is the legacy format consumed by the desktop app.
// Matches syfthub-desktop/types.go:231-241.
type ManifestPackage struct {
	Slug        string             `json:"slug"`
	Name        string             `json:"name"`
	Description string             `json:"description"`
	Type        PackageType        `json:"type"`
	Author      string             `json:"author,omitempty"`
	Version     string             `json:"version"`
	DownloadURL string             `json:"downloadUrl"`
	Tags        []string           `json:"tags,omitempty"`
	Config      []PackageConfigField `json:"config,omitempty"`
}

// Manifest is the top-level legacy structure.
type Manifest struct {
	Packages []ManifestPackage `json:"packages"`
}

// CreatePackageRequest is the metadata JSON for POST /api/v1/packages.
type CreatePackageRequest struct {
	Slug        string             `json:"slug"`
	Name        string             `json:"name"`
	Description string             `json:"description"`
	Type        PackageType        `json:"type"`
	Author      string             `json:"author"`
	Version     string             `json:"version"`
	Tags        []string           `json:"tags"`
	Config      []PackageConfigField `json:"config"`
}

// UpdatePackageRequest uses pointer fields for JSON merge-patch semantics.
type UpdatePackageRequest struct {
	Name        *string             `json:"name,omitempty"`
	Description *string             `json:"description,omitempty"`
	Type        *PackageType        `json:"type,omitempty"`
	Author      *string             `json:"author,omitempty"`
	Version     *string             `json:"version,omitempty"`
	Tags        *[]string           `json:"tags,omitempty"`
	Config      *[]PackageConfigField `json:"config,omitempty"`
}

// PackageListResponse is the paginated list response.
type PackageListResponse struct {
	Packages []Package `json:"packages"`
	Total    int       `json:"total"`
	Limit    int       `json:"limit"`
	Offset   int       `json:"offset"`
}

// ListOptions holds query parameters for listing packages.
type ListOptions struct {
	Type   string
	Tag    string
	Query  string
	Limit  int
	Offset int
}
