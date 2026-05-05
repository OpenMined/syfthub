package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
)

// Sentinel errors for errors.Is() matching.
var (
	ErrNotFound   = errors.New("not found")
	ErrConflict   = errors.New("conflict")
	ErrValidation = errors.New("validation error")
)

// NotFoundError indicates a resource was not found.
type NotFoundError struct {
	Slug string
}

func (e *NotFoundError) Error() string {
	return fmt.Sprintf("package %q not found", e.Slug)
}

func (e *NotFoundError) Unwrap() error { return ErrNotFound }

// ConflictError indicates a resource already exists.
type ConflictError struct {
	Slug string
}

func (e *ConflictError) Error() string {
	return fmt.Sprintf("package %q already exists", e.Slug)
}

func (e *ConflictError) Unwrap() error { return ErrConflict }

// ValidationError indicates invalid input.
type ValidationError struct {
	Field   string
	Message string
}

func (e *ValidationError) Error() string {
	if e.Field != "" {
		return fmt.Sprintf("validation error on %q: %s", e.Field, e.Message)
	}
	return fmt.Sprintf("validation error: %s", e.Message)
}

func (e *ValidationError) Unwrap() error { return ErrValidation }

// ProblemDetail implements RFC 9457 Problem Details for HTTP APIs.
type ProblemDetail struct {
	Type     string `json:"type"`
	Title    string `json:"title"`
	Status   int    `json:"status"`
	Detail   string `json:"detail,omitempty"`
	Instance string `json:"instance,omitempty"`
}

// writeProblem writes an RFC 9457 problem+json response.
func writeProblem(w http.ResponseWriter, status int, title, detail string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	p := ProblemDetail{
		Type:   "about:blank",
		Title:  title,
		Status: status,
		Detail: detail,
	}
	if err := json.NewEncoder(w).Encode(p); err != nil {
		slog.Error("failed to write problem response", "error", err)
	}
}

// writeErrorResponse maps typed errors to appropriate HTTP problem responses.
func writeErrorResponse(w http.ResponseWriter, err error) {
	var notFound *NotFoundError
	var conflict *ConflictError
	var validation *ValidationError

	switch {
	case errors.As(err, &notFound):
		writeProblem(w, http.StatusNotFound, "Not Found", notFound.Error())
	case errors.As(err, &conflict):
		writeProblem(w, http.StatusConflict, "Conflict", conflict.Error())
	case errors.As(err, &validation):
		writeProblem(w, http.StatusUnprocessableEntity, "Validation Error", validation.Error())
	default:
		slog.Error("internal error", "error", err)
		writeProblem(w, http.StatusInternalServerError, "Internal Server Error", "an unexpected error occurred")
	}
}
