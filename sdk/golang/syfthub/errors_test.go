package syfthub

import (
	"errors"
	"testing"
)

func TestSyftHubError(t *testing.T) {
	t.Run("with status code", func(t *testing.T) {
		err := newSyftHubError(500, "test error")
		expected := "syfthub: [500] test error"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})

	t.Run("without status code", func(t *testing.T) {
		err := newSyftHubError(0, "test error")
		expected := "syfthub: test error"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})

	t.Run("unwrap returns nil", func(t *testing.T) {
		err := newSyftHubError(500, "test")
		if err.Unwrap() != nil {
			t.Error("Unwrap should return nil")
		}
	})
}

func TestAuthenticationError(t *testing.T) {
	err := newAuthenticationError("invalid credentials")

	t.Run("error message", func(t *testing.T) {
		expected := "syfthub: [401] invalid credentials"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})

	t.Run("unwrap to sentinel", func(t *testing.T) {
		if !errors.Is(err, ErrAuthentication) {
			t.Error("should unwrap to ErrAuthentication")
		}
	})

	t.Run("status code", func(t *testing.T) {
		if err.StatusCode != 401 {
			t.Errorf("StatusCode = %d, want 401", err.StatusCode)
		}
	})
}

func TestAuthorizationError(t *testing.T) {
	err := newAuthorizationError("access denied")

	t.Run("error message", func(t *testing.T) {
		expected := "syfthub: [403] access denied"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})

	t.Run("unwrap to sentinel", func(t *testing.T) {
		if !errors.Is(err, ErrAuthorization) {
			t.Error("should unwrap to ErrAuthorization")
		}
	})
}

func TestNotFoundError(t *testing.T) {
	err := newNotFoundError("resource not found")

	t.Run("error message", func(t *testing.T) {
		expected := "syfthub: [404] resource not found"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})

	t.Run("unwrap to sentinel", func(t *testing.T) {
		if !errors.Is(err, ErrNotFound) {
			t.Error("should unwrap to ErrNotFound")
		}
	})
}

func TestValidationError(t *testing.T) {
	t.Run("with field errors", func(t *testing.T) {
		fieldErrors := map[string][]string{
			"email":    {"invalid format"},
			"password": {"too short", "must contain number"},
		}
		err := newValidationError("validation failed", fieldErrors)

		if !errors.Is(err, ErrValidation) {
			t.Error("should unwrap to ErrValidation")
		}

		// Error message should include field errors
		errMsg := err.Error()
		if errMsg == "" {
			t.Error("error message should not be empty")
		}
		if err.Errors == nil {
			t.Error("Errors map should not be nil")
		}
		if len(err.Errors["email"]) != 1 {
			t.Errorf("email errors = %d, want 1", len(err.Errors["email"]))
		}
		if len(err.Errors["password"]) != 2 {
			t.Errorf("password errors = %d, want 2", len(err.Errors["password"]))
		}
	})

	t.Run("without field errors", func(t *testing.T) {
		err := newValidationError("validation failed", nil)
		expected := "syfthub: [422] validation failed"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})
}

func TestAPIError(t *testing.T) {
	err := newAPIError(500, "internal server error")
	expected := "syfthub: [500] internal server error"
	if err.Error() != expected {
		t.Errorf("Error() = %q, want %q", err.Error(), expected)
	}
}

func TestNetworkError(t *testing.T) {
	t.Run("with cause", func(t *testing.T) {
		cause := errors.New("connection refused")
		err := newNetworkError(cause)

		if !errors.Is(err, ErrNetwork) {
			t.Error("should unwrap to ErrNetwork")
		}

		expected := "syfthub: network error: connection refused"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}

		if err.Cause != cause {
			t.Error("Cause should match original error")
		}
	})

	t.Run("without cause", func(t *testing.T) {
		err := &NetworkError{
			SyftHubError: newSyftHubError(0, "network error"),
			Cause:        nil,
		}
		expected := "syfthub: network error"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})

	t.Run("unwrap returns multiple errors", func(t *testing.T) {
		cause := errors.New("timeout")
		err := newNetworkError(cause)
		unwrapped := err.Unwrap()
		if len(unwrapped) != 2 {
			t.Errorf("Unwrap() length = %d, want 2", len(unwrapped))
		}
	})
}

func TestUserAlreadyExistsError(t *testing.T) {
	err := &UserAlreadyExistsError{
		SyftHubError: newSyftHubError(409, "conflict"),
		Field:        "username",
	}
	expected := "syfthub: user already exists: username is taken"
	if err.Error() != expected {
		t.Errorf("Error() = %q, want %q", err.Error(), expected)
	}
}

func TestConfigurationError(t *testing.T) {
	err := &ConfigurationError{
		SyftHubError: newSyftHubError(0, "missing URL"),
	}

	if !errors.Is(err, ErrConfiguration) {
		t.Error("should unwrap to ErrConfiguration")
	}
}

func TestChatError(t *testing.T) {
	err := newChatError("chat failed")

	if !errors.Is(err, ErrChat) {
		t.Error("should unwrap to ErrChat")
	}
}

func TestAggregatorError(t *testing.T) {
	err := &AggregatorError{
		ChatError: newChatError("aggregator unavailable"),
	}

	// Should still unwrap to ErrChat
	if !errors.Is(err, ErrChat) {
		t.Error("should unwrap to ErrChat")
	}
}

func TestRetrievalError(t *testing.T) {
	t.Run("with source", func(t *testing.T) {
		err := newRetrievalError("query failed", "docs-dataset", "timeout")
		expected := "syfthub: retrieval error from docs-dataset: query failed"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})

	t.Run("without source", func(t *testing.T) {
		err := &RetrievalError{
			ChatError: newChatError("query failed"),
			Source:    "",
		}
		expected := "syfthub: retrieval error: query failed"
		if err.Error() != expected {
			t.Errorf("Error() = %q, want %q", err.Error(), expected)
		}
	})
}

func TestGenerationError(t *testing.T) {
	err := newGenerationError("generation failed", "model-slug", "context too long")
	if !errors.Is(err, ErrChat) {
		t.Error("should unwrap to ErrChat")
	}
}

func TestEndpointResolutionError(t *testing.T) {
	err := newEndpointResolutionError("alice/my-model")
	expected := "syfthub: failed to resolve endpoint: alice/my-model"
	if err.Error() != expected {
		t.Errorf("Error() = %q, want %q", err.Error(), expected)
	}
	if err.Path != "alice/my-model" {
		t.Errorf("Path = %q, want alice/my-model", err.Path)
	}
}

func TestAccountingErrors(t *testing.T) {
	t.Run("AccountingAccountExistsError", func(t *testing.T) {
		err := &AccountingAccountExistsError{
			SyftHubError: newSyftHubError(409, "account exists"),
		}
		if !errors.Is(err, ErrAccounting) {
			t.Error("should unwrap to ErrAccounting")
		}
	})

	t.Run("InvalidAccountingPasswordError", func(t *testing.T) {
		err := &InvalidAccountingPasswordError{
			SyftHubError: newSyftHubError(401, "wrong password"),
		}
		if !errors.Is(err, ErrAccounting) {
			t.Error("should unwrap to ErrAccounting")
		}
	})

	t.Run("AccountingServiceUnavailableError", func(t *testing.T) {
		err := &AccountingServiceUnavailableError{
			SyftHubError: newSyftHubError(503, "service unavailable"),
		}
		if !errors.Is(err, ErrAccounting) {
			t.Error("should unwrap to ErrAccounting")
		}
	})
}

func TestSentinelErrors(t *testing.T) {
	testCases := []struct {
		name     string
		sentinel error
	}{
		{"ErrAuthentication", ErrAuthentication},
		{"ErrAuthorization", ErrAuthorization},
		{"ErrNotFound", ErrNotFound},
		{"ErrValidation", ErrValidation},
		{"ErrNetwork", ErrNetwork},
		{"ErrConfiguration", ErrConfiguration},
		{"ErrChat", ErrChat},
		{"ErrAccounting", ErrAccounting},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			if tc.sentinel == nil {
				t.Errorf("%s should not be nil", tc.name)
			}
			if tc.sentinel.Error() == "" {
				t.Errorf("%s should have non-empty error message", tc.name)
			}
		})
	}
}
