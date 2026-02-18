package syfthubapi

import (
	"errors"
	"fmt"
)

// Sentinel errors for use with errors.Is().
var (
	ErrConfiguration        = errors.New("configuration error")
	ErrAuthentication       = errors.New("authentication error")
	ErrAuthorization        = errors.New("authorization error")
	ErrSync                 = errors.New("sync error")
	ErrEndpointRegistration = errors.New("endpoint registration error")
	ErrPolicyDenied         = errors.New("policy denied")
	ErrEndpointNotFound     = errors.New("endpoint not found")
	ErrExecutionFailed      = errors.New("execution failed")
	ErrTimeout              = errors.New("timeout")
	ErrValidation           = errors.New("validation error")
	ErrTransport            = errors.New("transport error")
)

// SyftAPIError is the base error type for all syfthubapi errors.
type SyftAPIError struct {
	// Err is the underlying sentinel error.
	Err error

	// Message is a human-readable error message.
	Message string

	// Details contains additional error context.
	Details map[string]any
}

// Error implements the error interface.
func (e *SyftAPIError) Error() string {
	if e.Message != "" {
		return e.Message
	}
	if e.Err != nil {
		return e.Err.Error()
	}
	return "unknown error"
}

// Unwrap returns the underlying error for errors.Is() and errors.As().
func (e *SyftAPIError) Unwrap() error {
	return e.Err
}

// ConfigurationError indicates invalid or missing configuration.
type ConfigurationError struct {
	// Field is the configuration field with the error.
	Field string

	// Message describes the error.
	Message string

	// Value is the invalid value (if applicable).
	Value any
}

// Error implements the error interface.
func (e *ConfigurationError) Error() string {
	if e.Value != nil {
		return fmt.Sprintf("configuration error: %s: %s (got: %v)", e.Field, e.Message, e.Value)
	}
	return fmt.Sprintf("configuration error: %s: %s", e.Field, e.Message)
}

// Unwrap returns ErrConfiguration for errors.Is().
func (e *ConfigurationError) Unwrap() error {
	return ErrConfiguration
}

// AuthenticationError indicates authentication failure.
type AuthenticationError struct {
	// Message describes the error.
	Message string

	// Cause is the underlying error.
	Cause error
}

// Error implements the error interface.
func (e *AuthenticationError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("authentication error: %s: %v", e.Message, e.Cause)
	}
	return fmt.Sprintf("authentication error: %s", e.Message)
}

// Unwrap returns ErrAuthentication for errors.Is().
func (e *AuthenticationError) Unwrap() error {
	return ErrAuthentication
}

// AuthorizationError indicates authorization failure.
type AuthorizationError struct {
	// Message describes the error.
	Message string

	// User is the username that was denied.
	User string

	// Resource is the resource that was denied.
	Resource string
}

// Error implements the error interface.
func (e *AuthorizationError) Error() string {
	return fmt.Sprintf("authorization error: %s (user: %s, resource: %s)", e.Message, e.User, e.Resource)
}

// Unwrap returns ErrAuthorization for errors.Is().
func (e *AuthorizationError) Unwrap() error {
	return ErrAuthorization
}

// SyncError indicates endpoint synchronization failure.
type SyncError struct {
	// Message describes the error.
	Message string

	// Cause is the underlying error.
	Cause error

	// StatusCode is the HTTP status code (if applicable).
	StatusCode int
}

// Error implements the error interface.
func (e *SyncError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("sync error: %s: %v", e.Message, e.Cause)
	}
	if e.StatusCode != 0 {
		return fmt.Sprintf("sync error: %s (status: %d)", e.Message, e.StatusCode)
	}
	return fmt.Sprintf("sync error: %s", e.Message)
}

// Unwrap returns ErrSync for errors.Is().
func (e *SyncError) Unwrap() error {
	return ErrSync
}

// EndpointRegistrationError indicates invalid endpoint registration.
type EndpointRegistrationError struct {
	// Slug is the endpoint slug.
	Slug string

	// Field is the field with the error.
	Field string

	// Message describes the error.
	Message string
}

// Error implements the error interface.
func (e *EndpointRegistrationError) Error() string {
	return fmt.Sprintf("endpoint registration error: %s: %s: %s", e.Slug, e.Field, e.Message)
}

// Unwrap returns ErrEndpointRegistration for errors.Is().
func (e *EndpointRegistrationError) Unwrap() error {
	return ErrEndpointRegistration
}

// PolicyDeniedError indicates a policy denied the request.
type PolicyDeniedError struct {
	// Policy is the name of the policy that denied.
	Policy string

	// Reason is the denial reason.
	Reason string

	// User is the user that was denied.
	User string

	// Endpoint is the endpoint that was denied.
	Endpoint string
}

// Error implements the error interface.
func (e *PolicyDeniedError) Error() string {
	return fmt.Sprintf("policy denied: %s: %s (user: %s, endpoint: %s)", e.Policy, e.Reason, e.User, e.Endpoint)
}

// Unwrap returns ErrPolicyDenied for errors.Is().
func (e *PolicyDeniedError) Unwrap() error {
	return ErrPolicyDenied
}

// EndpointNotFoundError indicates the endpoint was not found.
type EndpointNotFoundError struct {
	// Slug is the endpoint slug that was not found.
	Slug string
}

// Error implements the error interface.
func (e *EndpointNotFoundError) Error() string {
	return fmt.Sprintf("endpoint not found: %s", e.Slug)
}

// Unwrap returns ErrEndpointNotFound for errors.Is().
func (e *EndpointNotFoundError) Unwrap() error {
	return ErrEndpointNotFound
}

// ExecutionError indicates handler execution failure.
type ExecutionError struct {
	// Endpoint is the endpoint slug.
	Endpoint string

	// Message describes the error.
	Message string

	// Cause is the underlying error.
	Cause error

	// ErrorType is the type of error from the handler.
	ErrorType string

	// Stderr contains stderr output (for subprocess execution).
	Stderr string
}

// Error implements the error interface.
func (e *ExecutionError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("execution error: %s: %s: %v", e.Endpoint, e.Message, e.Cause)
	}
	return fmt.Sprintf("execution error: %s: %s", e.Endpoint, e.Message)
}

// Unwrap returns ErrExecutionFailed for errors.Is().
func (e *ExecutionError) Unwrap() error {
	return ErrExecutionFailed
}

// TimeoutError indicates an operation timed out.
type TimeoutError struct {
	// Operation is the operation that timed out.
	Operation string

	// Duration is how long the operation ran.
	Duration string
}

// Error implements the error interface.
func (e *TimeoutError) Error() string {
	return fmt.Sprintf("timeout: %s after %s", e.Operation, e.Duration)
}

// Unwrap returns ErrTimeout for errors.Is().
func (e *TimeoutError) Unwrap() error {
	return ErrTimeout
}

// ValidationError indicates request validation failure.
type ValidationError struct {
	// Field is the field with the error.
	Field string

	// Message describes the error.
	Message string

	// Value is the invalid value.
	Value any
}

// Error implements the error interface.
func (e *ValidationError) Error() string {
	if e.Value != nil {
		return fmt.Sprintf("validation error: %s: %s (got: %v)", e.Field, e.Message, e.Value)
	}
	return fmt.Sprintf("validation error: %s: %s", e.Field, e.Message)
}

// Unwrap returns ErrValidation for errors.Is().
func (e *ValidationError) Unwrap() error {
	return ErrValidation
}

// TransportError indicates a transport-level error.
type TransportError struct {
	// Transport is the transport type (http, nats).
	Transport string

	// Message describes the error.
	Message string

	// Cause is the underlying error.
	Cause error
}

// Error implements the error interface.
func (e *TransportError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("transport error (%s): %s: %v", e.Transport, e.Message, e.Cause)
	}
	return fmt.Sprintf("transport error (%s): %s", e.Transport, e.Message)
}

// Unwrap returns ErrTransport for errors.Is().
func (e *TransportError) Unwrap() error {
	return ErrTransport
}

// FileLoadError indicates an error loading file-based endpoints.
type FileLoadError struct {
	// Path is the file or directory path.
	Path string

	// Message describes the error.
	Message string

	// Cause is the underlying error.
	Cause error
}

// Error implements the error interface.
func (e *FileLoadError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("file load error: %s: %s: %v", e.Path, e.Message, e.Cause)
	}
	return fmt.Sprintf("file load error: %s: %s", e.Path, e.Message)
}

// Unwrap returns the underlying cause.
func (e *FileLoadError) Unwrap() error {
	return e.Cause
}

// PolicyLoadError indicates an error loading a policy.
type PolicyLoadError struct {
	// Path is the policy file path.
	Path string

	// PolicyType is the policy type.
	PolicyType string

	// Message describes the error.
	Message string

	// Cause is the underlying error.
	Cause error
}

// Error implements the error interface.
func (e *PolicyLoadError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("policy load error: %s (%s): %s: %v", e.Path, e.PolicyType, e.Message, e.Cause)
	}
	return fmt.Sprintf("policy load error: %s (%s): %s", e.Path, e.PolicyType, e.Message)
}

// Unwrap returns the underlying cause.
func (e *PolicyLoadError) Unwrap() error {
	return e.Cause
}
