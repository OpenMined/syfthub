package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"fmt"
)

// buildZip creates an in-memory zip with slug/README.md, slug/runner.py,
// and optionally slug/pyproject.toml if pyproject is non-empty.
func buildZip(slug, readme, runner, pyproject string) ([]byte, string, error) {
	buf := new(bytes.Buffer)
	w := zip.NewWriter(buf)

	files := [][2]string{
		{slug + "/README.md", readme},
		{slug + "/runner.py", runner},
	}
	if pyproject != "" {
		files = append(files, [2]string{slug + "/pyproject.toml", pyproject})
	}
	for _, entry := range files {
		f, err := w.Create(entry[0])
		if err != nil {
			return nil, "", fmt.Errorf("create zip entry %s: %w", entry[0], err)
		}
		if _, err := f.Write([]byte(entry[1])); err != nil {
			return nil, "", fmt.Errorf("write zip entry %s: %w", entry[0], err)
		}
	}

	if err := w.Close(); err != nil {
		return nil, "", fmt.Errorf("close zip: %w", err)
	}

	data := buf.Bytes()
	return data, sha256Hex(data), nil
}

// sha256Hex returns the hex-encoded SHA-256 of data.
func sha256Hex(data []byte) string {
	h := sha256.Sum256(data)
	return fmt.Sprintf("%x", h)
}

// validateZipStructure checks that a zip is readable and non-empty.
func validateZipStructure(data []byte) error {
	r, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return &ValidationError{Field: "package", Message: "invalid zip file"}
	}
	if len(r.File) == 0 {
		return &ValidationError{Field: "package", Message: "zip file is empty"}
	}
	return nil
}
