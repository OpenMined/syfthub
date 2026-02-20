package syfthubapi

import (
	"errors"
	"fmt"
	"testing"
)

func TestSentinelErrors(t *testing.T) {
	// Verify all sentinel errors are distinct and non-nil
	sentinels := []error{
		ErrConfiguration,
		ErrAuthentication,
		ErrAuthorization,
		ErrSync,
		ErrEndpointRegistration,
		ErrPolicyDenied,
		ErrEndpointNotFound,
		ErrExecutionFailed,
		ErrTimeout,
		ErrValidation,
		ErrTransport,
	}

	for i, err := range sentinels {
		if err == nil {
			t.Errorf("sentinel error at index %d is nil", i)
		}
	}

	// Check uniqueness
	for i := 0; i < len(sentinels); i++ {
		for j := i + 1; j < len(sentinels); j++ {
			if errors.Is(sentinels[i], sentinels[j]) {
				t.Errorf("sentinel errors at indices %d and %d are not unique", i, j)
			}
		}
	}
}

func TestSyftAPIError(t *testing.T) {
	t.Run("error with message", func(t *testing.T) {
		err := &SyftAPIError{
			Err:     ErrConfiguration,
			Message: "custom message",
			Details: map[string]any{"key": "value"},
		}

		if err.Error() != "custom message" {
			t.Errorf("expected 'custom message', got %q", err.Error())
		}
		if !errors.Is(err, ErrConfiguration) {
			t.Error("expected errors.Is to return true for ErrConfiguration")
		}
	})

	t.Run("error without message uses underlying error", func(t *testing.T) {
		err := &SyftAPIError{
			Err: ErrAuthentication,
		}

		if err.Error() != "authentication error" {
			t.Errorf("expected 'authentication error', got %q", err.Error())
		}
	})

	t.Run("error without message or underlying error", func(t *testing.T) {
		err := &SyftAPIError{}

		if err.Error() != "unknown error" {
			t.Errorf("expected 'unknown error', got %q", err.Error())
		}
	})

	t.Run("unwrap returns underlying error", func(t *testing.T) {
		err := &SyftAPIError{Err: ErrTimeout}
		if err.Unwrap() != ErrTimeout {
			t.Error("Unwrap should return ErrTimeout")
		}
	})
}

func TestConfigurationError(t *testing.T) {
	tests := []struct {
		name     string
		err      *ConfigurationError
		expected string
	}{
		{
			name:     "with value",
			err:      &ConfigurationError{Field: "APIKey", Message: "required", Value: ""},
			expected: "configuration error: APIKey: required (got: )",
		},
		{
			name:     "without value",
			err:      &ConfigurationError{Field: "SyftHubURL", Message: "required but not set"},
			expected: "configuration error: SyftHubURL: required but not set",
		},
		{
			name:     "with non-nil value",
			err:      &ConfigurationError{Field: "Port", Message: "must be positive", Value: -1},
			expected: "configuration error: Port: must be positive (got: -1)",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.err.Error(); got != tt.expected {
				t.Errorf("Error() = %q, want %q", got, tt.expected)
			}
			if !errors.Is(tt.err, ErrConfiguration) {
				t.Error("expected errors.Is to return true for ErrConfiguration")
			}
		})
	}
}

func TestAuthenticationError(t *testing.T) {
	t.Run("with cause", func(t *testing.T) {
		cause := fmt.Errorf("network error")
		err := &AuthenticationError{
			Message: "token verification failed",
			Cause:   cause,
		}

		expected := "authentication error: token verification failed: network error"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
		if !errors.Is(err, ErrAuthentication) {
			t.Error("expected errors.Is to return true for ErrAuthentication")
		}
	})

	t.Run("without cause", func(t *testing.T) {
		err := &AuthenticationError{Message: "invalid credentials"}

		expected := "authentication error: invalid credentials"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
	})
}

func TestAuthorizationError(t *testing.T) {
	err := &AuthorizationError{
		Message:  "access denied",
		User:     "testuser",
		Resource: "/api/v1/endpoints",
	}

	expected := "authorization error: access denied (user: testuser, resource: /api/v1/endpoints)"
	if err.Error() != expected {
		t.Errorf("expected %q, got %q", expected, err.Error())
	}
	if !errors.Is(err, ErrAuthorization) {
		t.Error("expected errors.Is to return true for ErrAuthorization")
	}
}

func TestSyncError(t *testing.T) {
	tests := []struct {
		name     string
		err      *SyncError
		expected string
	}{
		{
			name: "with cause",
			err: &SyncError{
				Message: "failed to sync endpoints",
				Cause:   fmt.Errorf("connection refused"),
			},
			expected: "sync error: failed to sync endpoints: connection refused",
		},
		{
			name: "with status code",
			err: &SyncError{
				Message:    "server rejected request",
				StatusCode: 503,
			},
			expected: "sync error: server rejected request (status: 503)",
		},
		{
			name: "message only",
			err: &SyncError{
				Message: "sync failed",
			},
			expected: "sync error: sync failed",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.err.Error(); got != tt.expected {
				t.Errorf("Error() = %q, want %q", got, tt.expected)
			}
			if !errors.Is(tt.err, ErrSync) {
				t.Error("expected errors.Is to return true for ErrSync")
			}
		})
	}
}

func TestEndpointRegistrationError(t *testing.T) {
	err := &EndpointRegistrationError{
		Slug:    "my-endpoint",
		Field:   "handler",
		Message: "handler is required",
	}

	expected := "endpoint registration error: my-endpoint: handler: handler is required"
	if err.Error() != expected {
		t.Errorf("expected %q, got %q", expected, err.Error())
	}
	if !errors.Is(err, ErrEndpointRegistration) {
		t.Error("expected errors.Is to return true for ErrEndpointRegistration")
	}
}

func TestPolicyDeniedError(t *testing.T) {
	err := &PolicyDeniedError{
		Policy:   "rate_limit",
		Reason:   "exceeded 100 requests per minute",
		User:     "testuser",
		Endpoint: "my-model",
	}

	expected := "policy denied: rate_limit: exceeded 100 requests per minute (user: testuser, endpoint: my-model)"
	if err.Error() != expected {
		t.Errorf("expected %q, got %q", expected, err.Error())
	}
	if !errors.Is(err, ErrPolicyDenied) {
		t.Error("expected errors.Is to return true for ErrPolicyDenied")
	}
}

func TestEndpointNotFoundError(t *testing.T) {
	err := &EndpointNotFoundError{Slug: "nonexistent-endpoint"}

	expected := "endpoint not found: nonexistent-endpoint"
	if err.Error() != expected {
		t.Errorf("expected %q, got %q", expected, err.Error())
	}
	if !errors.Is(err, ErrEndpointNotFound) {
		t.Error("expected errors.Is to return true for ErrEndpointNotFound")
	}
}

func TestExecutionError(t *testing.T) {
	t.Run("with cause", func(t *testing.T) {
		err := &ExecutionError{
			Endpoint:  "my-model",
			Message:   "handler panicked",
			Cause:     fmt.Errorf("nil pointer dereference"),
			ErrorType: "PanicError",
		}

		expected := "execution error: my-model: handler panicked: nil pointer dereference"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
		if !errors.Is(err, ErrExecutionFailed) {
			t.Error("expected errors.Is to return true for ErrExecutionFailed")
		}
	})

	t.Run("without cause", func(t *testing.T) {
		err := &ExecutionError{
			Endpoint: "my-model",
			Message:  "timeout during execution",
		}

		expected := "execution error: my-model: timeout during execution"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
	})

	t.Run("with stderr", func(t *testing.T) {
		err := &ExecutionError{
			Endpoint: "my-endpoint",
			Message:  "subprocess failed",
			Stderr:   "ImportError: No module named 'missing'",
		}

		if err.Stderr != "ImportError: No module named 'missing'" {
			t.Error("Stderr field not preserved")
		}
	})
}

func TestTimeoutError(t *testing.T) {
	err := &TimeoutError{
		Operation: "endpoint execution",
		Duration:  "30s",
	}

	expected := "timeout: endpoint execution after 30s"
	if err.Error() != expected {
		t.Errorf("expected %q, got %q", expected, err.Error())
	}
	if !errors.Is(err, ErrTimeout) {
		t.Error("expected errors.Is to return true for ErrTimeout")
	}
}

func TestValidationError(t *testing.T) {
	tests := []struct {
		name     string
		err      *ValidationError
		expected string
	}{
		{
			name:     "with value",
			err:      &ValidationError{Field: "limit", Message: "must be positive", Value: -5},
			expected: "validation error: limit: must be positive (got: -5)",
		},
		{
			name:     "without value",
			err:      &ValidationError{Field: "query", Message: "required"},
			expected: "validation error: query: required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.err.Error(); got != tt.expected {
				t.Errorf("Error() = %q, want %q", got, tt.expected)
			}
			if !errors.Is(tt.err, ErrValidation) {
				t.Error("expected errors.Is to return true for ErrValidation")
			}
		})
	}
}

func TestTransportError(t *testing.T) {
	t.Run("with cause", func(t *testing.T) {
		err := &TransportError{
			Transport: "http",
			Message:   "failed to connect",
			Cause:     fmt.Errorf("connection refused"),
		}

		expected := "transport error (http): failed to connect: connection refused"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
		if !errors.Is(err, ErrTransport) {
			t.Error("expected errors.Is to return true for ErrTransport")
		}
	})

	t.Run("without cause", func(t *testing.T) {
		err := &TransportError{
			Transport: "nats",
			Message:   "subscription failed",
		}

		expected := "transport error (nats): subscription failed"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
	})
}

func TestFileLoadError(t *testing.T) {
	t.Run("with cause", func(t *testing.T) {
		cause := fmt.Errorf("file not found")
		err := &FileLoadError{
			Path:    "/path/to/endpoint",
			Message: "failed to load README.md",
			Cause:   cause,
		}

		expected := "file load error: /path/to/endpoint: failed to load README.md: file not found"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
		// FileLoadError unwraps to its Cause, not a sentinel
		if err.Unwrap() != cause {
			t.Error("Unwrap should return the Cause")
		}
	})

	t.Run("without cause", func(t *testing.T) {
		err := &FileLoadError{
			Path:    "/path/to/endpoint",
			Message: "invalid YAML",
		}

		expected := "file load error: /path/to/endpoint: invalid YAML"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
	})
}

func TestPolicyLoadError(t *testing.T) {
	t.Run("with cause", func(t *testing.T) {
		cause := fmt.Errorf("syntax error at line 5")
		err := &PolicyLoadError{
			Path:       "/path/to/policy.yaml",
			PolicyType: "rate_limit",
			Message:    "failed to parse",
			Cause:      cause,
		}

		expected := "policy load error: /path/to/policy.yaml (rate_limit): failed to parse: syntax error at line 5"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
		// PolicyLoadError unwraps to its Cause
		if err.Unwrap() != cause {
			t.Error("Unwrap should return the Cause")
		}
	})

	t.Run("without cause", func(t *testing.T) {
		err := &PolicyLoadError{
			Path:       "/path/to/policy.yaml",
			PolicyType: "access_group",
			Message:    "missing required field",
		}

		expected := "policy load error: /path/to/policy.yaml (access_group): missing required field"
		if err.Error() != expected {
			t.Errorf("expected %q, got %q", expected, err.Error())
		}
	})
}

func TestErrorsAs(t *testing.T) {
	// Test errors.As functionality for type extraction
	t.Run("ConfigurationError", func(t *testing.T) {
		err := &ConfigurationError{Field: "test", Message: "test message"}
		var configErr *ConfigurationError
		if !errors.As(err, &configErr) {
			t.Error("errors.As should work with ConfigurationError")
		}
		if configErr.Field != "test" {
			t.Error("extracted error should have correct Field")
		}
	})

	t.Run("AuthenticationError", func(t *testing.T) {
		err := &AuthenticationError{Message: "test"}
		var authErr *AuthenticationError
		if !errors.As(err, &authErr) {
			t.Error("errors.As should work with AuthenticationError")
		}
	})

	t.Run("PolicyDeniedError", func(t *testing.T) {
		err := &PolicyDeniedError{Policy: "test", Reason: "testing"}
		var policyErr *PolicyDeniedError
		if !errors.As(err, &policyErr) {
			t.Error("errors.As should work with PolicyDeniedError")
		}
		if policyErr.Policy != "test" {
			t.Error("extracted error should have correct Policy")
		}
	})

	t.Run("ExecutionError", func(t *testing.T) {
		err := &ExecutionError{Endpoint: "test-ep", Message: "failed"}
		var execErr *ExecutionError
		if !errors.As(err, &execErr) {
			t.Error("errors.As should work with ExecutionError")
		}
		if execErr.Endpoint != "test-ep" {
			t.Error("extracted error should have correct Endpoint")
		}
	})
}

func TestWrappedErrors(t *testing.T) {
	// Test that wrapped errors work correctly with errors.Is
	t.Run("wrapped ConfigurationError", func(t *testing.T) {
		configErr := &ConfigurationError{Field: "test", Message: "inner"}
		wrapped := fmt.Errorf("outer context: %w", configErr)

		if !errors.Is(wrapped, ErrConfiguration) {
			t.Error("wrapped ConfigurationError should match ErrConfiguration")
		}
	})

	t.Run("wrapped AuthenticationError", func(t *testing.T) {
		authErr := &AuthenticationError{Message: "inner"}
		wrapped := fmt.Errorf("outer: %w", authErr)

		if !errors.Is(wrapped, ErrAuthentication) {
			t.Error("wrapped AuthenticationError should match ErrAuthentication")
		}
	})

	t.Run("double wrapped error", func(t *testing.T) {
		inner := &ExecutionError{Endpoint: "ep", Message: "inner"}
		middle := fmt.Errorf("middle: %w", inner)
		outer := fmt.Errorf("outer: %w", middle)

		if !errors.Is(outer, ErrExecutionFailed) {
			t.Error("double wrapped ExecutionError should match ErrExecutionFailed")
		}

		var execErr *ExecutionError
		if !errors.As(outer, &execErr) {
			t.Error("errors.As should work through wrapper chain")
		}
	})
}
