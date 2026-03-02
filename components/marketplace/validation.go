package main

import (
	"fmt"
	"regexp"
)

var (
	slugRegex   = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$`)
	semverRegex = regexp.MustCompile(`^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$`)
)

// ValidateCreateRequest validates all fields of a CreatePackageRequest.
func ValidateCreateRequest(req *CreatePackageRequest) error {
	if req.Slug == "" {
		return &ValidationError{Field: "slug", Message: "required"}
	}
	if len(req.Slug) > 64 || !slugRegex.MatchString(req.Slug) {
		return &ValidationError{Field: "slug", Message: "must be 1-64 lowercase alphanumeric chars or hyphens, starting and ending with alphanumeric"}
	}

	if req.Name == "" {
		return &ValidationError{Field: "name", Message: "required"}
	}
	if len(req.Name) > 200 {
		return &ValidationError{Field: "name", Message: "must be at most 200 characters"}
	}

	if req.Description == "" {
		return &ValidationError{Field: "description", Message: "required"}
	}
	if len(req.Description) > 2000 {
		return &ValidationError{Field: "description", Message: "must be at most 2000 characters"}
	}

	if !req.Type.Valid() {
		return &ValidationError{Field: "type", Message: fmt.Sprintf("must be %q or %q", PackageTypeModel, PackageTypeDataSource)}
	}

	if req.Author == "" {
		return &ValidationError{Field: "author", Message: "required"}
	}

	if req.Version == "" {
		return &ValidationError{Field: "version", Message: "required"}
	}
	if !semverRegex.MatchString(req.Version) {
		return &ValidationError{Field: "version", Message: "must be valid semver (e.g. 1.0.0)"}
	}

	if len(req.Tags) > 20 {
		return &ValidationError{Field: "tags", Message: "must have at most 20 tags"}
	}
	for i, tag := range req.Tags {
		if tag == "" || len(tag) > 50 {
			return &ValidationError{Field: fmt.Sprintf("tags[%d]", i), Message: "each tag must be 1-50 characters"}
		}
	}

	return nil
}

// ValidateUpdateRequest validates non-nil fields of an UpdatePackageRequest.
func ValidateUpdateRequest(req *UpdatePackageRequest) error {
	if req.Name != nil {
		if *req.Name == "" {
			return &ValidationError{Field: "name", Message: "must not be empty"}
		}
		if len(*req.Name) > 200 {
			return &ValidationError{Field: "name", Message: "must be at most 200 characters"}
		}
	}

	if req.Description != nil {
		if *req.Description == "" {
			return &ValidationError{Field: "description", Message: "must not be empty"}
		}
		if len(*req.Description) > 2000 {
			return &ValidationError{Field: "description", Message: "must be at most 2000 characters"}
		}
	}

	if req.Type != nil && !req.Type.Valid() {
		return &ValidationError{Field: "type", Message: fmt.Sprintf("must be %q or %q", PackageTypeModel, PackageTypeDataSource)}
	}

	if req.Author != nil && *req.Author == "" {
		return &ValidationError{Field: "author", Message: "must not be empty"}
	}

	if req.Version != nil {
		if *req.Version == "" {
			return &ValidationError{Field: "version", Message: "must not be empty"}
		}
		if !semverRegex.MatchString(*req.Version) {
			return &ValidationError{Field: "version", Message: "must be valid semver (e.g. 1.0.0)"}
		}
	}

	if req.Tags != nil {
		if len(*req.Tags) > 20 {
			return &ValidationError{Field: "tags", Message: "must have at most 20 tags"}
		}
		for i, tag := range *req.Tags {
			if tag == "" || len(tag) > 50 {
				return &ValidationError{Field: fmt.Sprintf("tags[%d]", i), Message: "each tag must be 1-50 characters"}
			}
		}
	}

	return nil
}
