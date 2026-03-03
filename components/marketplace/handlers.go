package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
)

// handleHealth returns server health and package count.
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	count, err := s.store.Count(r.Context())
	if err != nil {
		s.logger.Error("health check failed", "error", err)
		writeJSON(w, http.StatusInternalServerError, map[string]any{"status": "unhealthy"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "healthy", "packages": count})
}

// handleListPackages returns a paginated list of packages.
func (s *Server) handleListPackages(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	offset, _ := strconv.Atoi(q.Get("offset"))
	if limit <= 0 {
		limit = 20
	}

	opts := ListOptions{
		Type:   q.Get("type"),
		Tag:    q.Get("tag"),
		Query:  q.Get("q"),
		Limit:  limit,
		Offset: offset,
	}

	packages, total, err := s.store.List(r.Context(), opts)
	if err != nil {
		writeErrorResponse(w, err)
		return
	}

	// Compute download URLs
	for i := range packages {
		packages[i].DownloadURL = fmt.Sprintf("%s/api/v1/packages/%s/download", s.baseURL, packages[i].Slug)
	}

	writeJSON(w, http.StatusOK, PackageListResponse{
		Packages: packages,
		Total:    total,
		Limit:    opts.Limit,
		Offset:   opts.Offset,
	})
}

// handleGetPackage returns a single package by slug.
func (s *Server) handleGetPackage(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	pkg, err := s.store.Get(r.Context(), slug)
	if err != nil {
		writeErrorResponse(w, err)
		return
	}
	pkg.DownloadURL = fmt.Sprintf("%s/api/v1/packages/%s/download", s.baseURL, pkg.Slug)
	writeJSON(w, http.StatusOK, pkg)
}

// handleCreatePackage creates a new package from multipart form data.
func (s *Server) handleCreatePackage(w http.ResponseWriter, r *http.Request) {
	// Parse multipart form (32MB max)
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeProblem(w, http.StatusBadRequest, "Bad Request", "invalid multipart form: "+err.Error())
		return
	}

	// Parse metadata JSON
	metadataStr := r.FormValue("metadata")
	if metadataStr == "" {
		writeProblem(w, http.StatusBadRequest, "Bad Request", "missing 'metadata' form field")
		return
	}

	var req CreatePackageRequest
	if err := json.Unmarshal([]byte(metadataStr), &req); err != nil {
		writeProblem(w, http.StatusBadRequest, "Bad Request", "invalid metadata JSON: "+err.Error())
		return
	}

	if err := ValidateCreateRequest(&req); err != nil {
		writeErrorResponse(w, err)
		return
	}

	// Read zip file
	file, _, err := r.FormFile("package")
	if err != nil {
		writeProblem(w, http.StatusBadRequest, "Bad Request", "missing 'package' zip file")
		return
	}
	defer file.Close()

	zipData, err := io.ReadAll(io.LimitReader(file, 50<<20)) // 50MB limit
	if err != nil {
		writeProblem(w, http.StatusBadRequest, "Bad Request", "failed to read zip file")
		return
	}

	if err := validateZipStructure(zipData); err != nil {
		writeErrorResponse(w, err)
		return
	}

	zipHash := sha256Hex(zipData)

	if req.Tags == nil {
		req.Tags = []string{}
	}
	if req.Config == nil {
		req.Config = []PackageConfigField{}
	}

	pkg := &Package{
		Slug:        req.Slug,
		Name:        req.Name,
		Description: req.Description,
		Type:        req.Type,
		Author:      req.Author,
		Version:     req.Version,
		Tags:        req.Tags,
		Config:      req.Config,
		ZipSize:     int64(len(zipData)),
		ZipSHA256:   zipHash,
	}

	if err := s.store.Create(r.Context(), pkg); err != nil {
		writeErrorResponse(w, err)
		return
	}

	if err := s.store.SetZip(r.Context(), pkg.Slug, zipData, zipHash); err != nil {
		writeErrorResponse(w, err)
		return
	}

	pkg.DownloadURL = fmt.Sprintf("%s/api/v1/packages/%s/download", s.baseURL, pkg.Slug)

	w.Header().Set("Location", fmt.Sprintf("/api/v1/packages/%s", pkg.Slug))
	writeJSON(w, http.StatusCreated, pkg)
}

// handleUpdatePackage applies a JSON merge-patch to an existing package.
func (s *Server) handleUpdatePackage(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")

	var req UpdatePackageRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeProblem(w, http.StatusBadRequest, "Bad Request", "invalid JSON: "+err.Error())
		return
	}

	if err := ValidateUpdateRequest(&req); err != nil {
		writeErrorResponse(w, err)
		return
	}

	pkg, err := s.store.Update(r.Context(), slug, &req)
	if err != nil {
		writeErrorResponse(w, err)
		return
	}

	pkg.DownloadURL = fmt.Sprintf("%s/api/v1/packages/%s/download", s.baseURL, pkg.Slug)
	writeJSON(w, http.StatusOK, pkg)
}

// handleDeletePackage removes a package.
func (s *Server) handleDeletePackage(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	if err := s.store.Delete(r.Context(), slug); err != nil {
		writeErrorResponse(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// handleDownloadPackage streams the package zip with ETag caching.
func (s *Server) handleDownloadPackage(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	data, sha256, err := s.store.GetZip(r.Context(), slug)
	if err != nil {
		writeErrorResponse(w, err)
		return
	}

	etag := `"` + sha256 + `"`
	w.Header().Set("ETag", etag)

	if match := r.Header.Get("If-None-Match"); match == etag {
		w.WriteHeader(http.StatusNotModified)
		return
	}

	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s.zip"`, slug))
	w.Header().Set("Content-Length", strconv.Itoa(len(data)))
	w.WriteHeader(http.StatusOK)
	w.Write(data)
}

// handleManifest returns the legacy manifest format for the desktop app.
func (s *Server) handleManifest(w http.ResponseWriter, r *http.Request) {
	packages, _, err := s.store.List(r.Context(), ListOptions{Limit: 1000})
	if err != nil {
		writeErrorResponse(w, err)
		return
	}

	manifest := Manifest{Packages: make([]ManifestPackage, len(packages))}
	for i, p := range packages {
		manifest.Packages[i] = ManifestPackage{
			Slug:        p.Slug,
			Name:        p.Name,
			Description: p.Description,
			Type:        p.Type,
			Author:      p.Author,
			Version:     p.Version,
			DownloadURL: fmt.Sprintf("%s/packages/%s.zip", s.baseURL, p.Slug),
			Tags:        p.Tags,
			Config:      p.Config,
		}
		if manifest.Packages[i].Tags == nil {
			manifest.Packages[i].Tags = []string{}
		}
		if manifest.Packages[i].Config == nil {
			manifest.Packages[i].Config = []PackageConfigField{}
		}
	}

	writeJSON(w, http.StatusOK, manifest)
}

// handleLegacyDownload serves /packages/{slug}.zip for the desktop app.
func (s *Server) handleLegacyDownload(w http.ResponseWriter, r *http.Request) {
	file := r.PathValue("file")
	slug := strings.TrimSuffix(file, ".zip")
	if slug == file {
		writeProblem(w, http.StatusNotFound, "Not Found", "expected .zip extension")
		return
	}

	data, sha256, err := s.store.GetZip(r.Context(), slug)
	if err != nil {
		writeErrorResponse(w, err)
		return
	}

	etag := `"` + sha256 + `"`
	w.Header().Set("ETag", etag)

	if match := r.Header.Get("If-None-Match"); match == etag {
		w.WriteHeader(http.StatusNotModified)
		return
	}

	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Length", strconv.Itoa(len(data)))
	w.WriteHeader(http.StatusOK)
	w.Write(data)
}

// writeJSON writes a JSON response with the given status code.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
