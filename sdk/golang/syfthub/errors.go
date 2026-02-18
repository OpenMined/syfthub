// Package syfthub provides a Go client for the SyftHub API.
package syfthub

import (
	"errors"
	"fmt"
)

// Sentinel errors for error checking with errors.Is().
var (
	// ErrAuthentication indicates authentication failure (401).
	ErrAuthentication = errors.New("authentication failed")

	// ErrAuthorization indicates authorization failure (403).
	ErrAuthorization = errors.New("authorization failed")

	// ErrNotFound indicates resource not found (404).
	ErrNotFound = errors.New("resource not found")

	// ErrValidation indicates validation failure (422).
	ErrValidation = errors.New("validation failed")

	// ErrNetwork indicates a network-level error.
	ErrNetwork = errors.New("network error")

	// ErrConfiguration indicates SDK configuration error.
	ErrConfiguration = errors.New("configuration error")

	// ErrChat indicates a chat-related error.
	ErrChat = errors.New("chat error")

	// ErrAccounting indicates an accounting service error.
	ErrAccounting = errors.New("accounting error")
)

// SyftHubError is the base error type for all API errors.
type SyftHubError struct {
	StatusCode int
	Message    string
	Details    map[string]interface{}
}

// Error implements the error interface.
func (e *SyftHubError) Error() string {
	if e.StatusCode > 0 {
		return fmt.Sprintf("syfthub: [%d] %s", e.StatusCode, e.Message)
	}
	return fmt.Sprintf("syfthub: %s", e.Message)
}

// Unwrap returns nil as SyftHubError is the base error.
func (e *SyftHubError) Unwrap() error {
	return nil
}

// AuthenticationError represents a 401 Unauthorized error.
type AuthenticationError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *AuthenticationError) Unwrap() error {
	return ErrAuthentication
}

// AuthorizationError represents a 403 Forbidden error.
type AuthorizationError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *AuthorizationError) Unwrap() error {
	return ErrAuthorization
}

// NotFoundError represents a 404 Not Found error.
type NotFoundError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *NotFoundError) Unwrap() error {
	return ErrNotFound
}

// ValidationError represents a 422 Unprocessable Entity error with field-level details.
type ValidationError struct {
	*SyftHubError
	Errors map[string][]string
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *ValidationError) Unwrap() error {
	return ErrValidation
}

// Error provides detailed validation error message.
func (e *ValidationError) Error() string {
	if len(e.Errors) > 0 {
		return fmt.Sprintf("syfthub: [%d] validation failed: %v", e.StatusCode, e.Errors)
	}
	return e.SyftHubError.Error()
}

// APIError represents a general API error.
type APIError struct {
	*SyftHubError
}

// NetworkError represents a network-level error (connection, timeout, etc.).
type NetworkError struct {
	*SyftHubError
	Cause error
}

// Unwrap returns the underlying cause and sentinel error.
func (e *NetworkError) Unwrap() []error {
	return []error{ErrNetwork, e.Cause}
}

// Error provides detailed network error message.
func (e *NetworkError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("syfthub: network error: %v", e.Cause)
	}
	return "syfthub: network error"
}

// UserAlreadyExistsError indicates a user registration conflict.
type UserAlreadyExistsError struct {
	*SyftHubError
	Field string // "username" or "email"
}

// Error provides detailed conflict error message.
func (e *UserAlreadyExistsError) Error() string {
	return fmt.Sprintf("syfthub: user already exists: %s is taken", e.Field)
}

// ConfigurationError indicates SDK configuration issues.
type ConfigurationError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *ConfigurationError) Unwrap() error {
	return ErrConfiguration
}

// ChatError is the base type for chat-related errors.
type ChatError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *ChatError) Unwrap() error {
	return ErrChat
}

// AggregatorError represents an error from the aggregator service.
type AggregatorError struct {
	*ChatError
}

// RetrievalError represents an error during RAG retrieval.
type RetrievalError struct {
	*ChatError
	Source string
}

// Error provides detailed retrieval error message.
func (e *RetrievalError) Error() string {
	if e.Source != "" {
		return fmt.Sprintf("syfthub: retrieval error from %s: %s", e.Source, e.Message)
	}
	return fmt.Sprintf("syfthub: retrieval error: %s", e.Message)
}

// GenerationError represents an error during model generation.
type GenerationError struct {
	*ChatError
}

// EndpointResolutionError represents an error resolving an endpoint path.
type EndpointResolutionError struct {
	*ChatError
	Path string
}

// Error provides detailed endpoint resolution error message.
func (e *EndpointResolutionError) Error() string {
	return fmt.Sprintf("syfthub: failed to resolve endpoint: %s", e.Path)
}

// AccountingAccountExistsError indicates the accounting account already exists.
type AccountingAccountExistsError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *AccountingAccountExistsError) Unwrap() error {
	return ErrAccounting
}

// InvalidAccountingPasswordError indicates wrong accounting password.
type InvalidAccountingPasswordError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *InvalidAccountingPasswordError) Unwrap() error {
	return ErrAccounting
}

// AccountingServiceUnavailableError indicates the accounting service is unavailable.
type AccountingServiceUnavailableError struct {
	*SyftHubError
}

// Unwrap returns the sentinel error for errors.Is() checking.
func (e *AccountingServiceUnavailableError) Unwrap() error {
	return ErrAccounting
}

// newSyftHubError creates a new base SyftHubError.
func newSyftHubError(statusCode int, message string) *SyftHubError {
	return &SyftHubError{
		StatusCode: statusCode,
		Message:    message,
	}
}

// newAuthenticationError creates a new AuthenticationError.
func newAuthenticationError(message string) *AuthenticationError {
	return &AuthenticationError{
		SyftHubError: newSyftHubError(401, message),
	}
}

// newAuthorizationError creates a new AuthorizationError.
func newAuthorizationError(message string) *AuthorizationError {
	return &AuthorizationError{
		SyftHubError: newSyftHubError(403, message),
	}
}

// newNotFoundError creates a new NotFoundError.
func newNotFoundError(message string) *NotFoundError {
	return &NotFoundError{
		SyftHubError: newSyftHubError(404, message),
	}
}

// newValidationError creates a new ValidationError.
func newValidationError(message string, errors map[string][]string) *ValidationError {
	return &ValidationError{
		SyftHubError: newSyftHubError(422, message),
		Errors:       errors,
	}
}

// newAPIError creates a new APIError.
func newAPIError(statusCode int, message string) *APIError {
	return &APIError{
		SyftHubError: newSyftHubError(statusCode, message),
	}
}

// newNetworkError creates a new NetworkError.
func newNetworkError(cause error) *NetworkError {
	return &NetworkError{
		SyftHubError: newSyftHubError(0, "network error"),
		Cause:        cause,
	}
}

// newChatError creates a new ChatError.
func newChatError(message string) *ChatError {
	return &ChatError{
		SyftHubError: newSyftHubError(0, message),
	}
}

// newEndpointResolutionError creates a new EndpointResolutionError.
func newEndpointResolutionError(path string) *EndpointResolutionError {
	return &EndpointResolutionError{
		ChatError: newChatError("failed to resolve endpoint"),
		Path:      path,
	}
}

// newRetrievalError creates a new RetrievalError.
func newRetrievalError(message, sourcePath, detail string) *RetrievalError {
	return &RetrievalError{
		ChatError: newChatError(message),
		Source:    sourcePath,
	}
}

// newGenerationError creates a new GenerationError.
func newGenerationError(message, modelSlug, detail string) *GenerationError {
	return &GenerationError{
		ChatError: newChatError(message),
	}
}
