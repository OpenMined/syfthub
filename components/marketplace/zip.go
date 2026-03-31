package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"fmt"
)

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
