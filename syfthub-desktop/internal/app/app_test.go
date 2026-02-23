package app

import (
	"os"
	"testing"
	"time"
)

func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()

	if cfg == nil {
		t.Fatal("DefaultConfig returned nil")
	}
	if cfg.EndpointsPath != "./endpoints" {
		t.Errorf("EndpointsPath = %q, want %q", cfg.EndpointsPath, "./endpoints")
	}
	if cfg.PythonPath != "" {
		t.Errorf("PythonPath = %q, want empty string", cfg.PythonPath)
	}
	if !cfg.UseEmbeddedPython {
		t.Error("UseEmbeddedPython should be true by default")
	}
	if !cfg.WatchEnabled {
		t.Error("WatchEnabled should be true by default")
	}
	if cfg.WatchDebounce != time.Second {
		t.Errorf("WatchDebounce = %v, want %v", cfg.WatchDebounce, time.Second)
	}
	if cfg.LogLevel != "INFO" {
		t.Errorf("LogLevel = %q, want %q", cfg.LogLevel, "INFO")
	}
}

func TestConfigFromEnv(t *testing.T) {
	// Save original env vars
	origEndpointsPath := os.Getenv("ENDPOINTS_PATH")
	origPythonPath := os.Getenv("PYTHON_PATH")
	origUseEmbeddedPython := os.Getenv("USE_EMBEDDED_PYTHON")
	origLogLevel := os.Getenv("LOG_LEVEL")
	origWatchEnabled := os.Getenv("WATCH_ENABLED")

	// Restore env vars after test
	defer func() {
		setEnvOrUnset("ENDPOINTS_PATH", origEndpointsPath)
		setEnvOrUnset("PYTHON_PATH", origPythonPath)
		setEnvOrUnset("USE_EMBEDDED_PYTHON", origUseEmbeddedPython)
		setEnvOrUnset("LOG_LEVEL", origLogLevel)
		setEnvOrUnset("WATCH_ENABLED", origWatchEnabled)
	}()

	t.Run("default values when env vars not set", func(t *testing.T) {
		// Clear env vars
		os.Unsetenv("ENDPOINTS_PATH")
		os.Unsetenv("PYTHON_PATH")
		os.Unsetenv("USE_EMBEDDED_PYTHON")
		os.Unsetenv("LOG_LEVEL")
		os.Unsetenv("WATCH_ENABLED")

		cfg := ConfigFromEnv()

		if cfg.EndpointsPath != "./endpoints" {
			t.Errorf("EndpointsPath = %q, want %q", cfg.EndpointsPath, "./endpoints")
		}
		if cfg.LogLevel != "INFO" {
			t.Errorf("LogLevel = %q, want %q", cfg.LogLevel, "INFO")
		}
	})

	t.Run("custom ENDPOINTS_PATH", func(t *testing.T) {
		os.Setenv("ENDPOINTS_PATH", "/custom/endpoints")
		defer os.Unsetenv("ENDPOINTS_PATH")

		cfg := ConfigFromEnv()

		if cfg.EndpointsPath != "/custom/endpoints" {
			t.Errorf("EndpointsPath = %q, want %q", cfg.EndpointsPath, "/custom/endpoints")
		}
	})

	t.Run("custom PYTHON_PATH disables embedded Python", func(t *testing.T) {
		os.Setenv("PYTHON_PATH", "/usr/bin/python3")
		defer os.Unsetenv("PYTHON_PATH")

		cfg := ConfigFromEnv()

		if cfg.PythonPath != "/usr/bin/python3" {
			t.Errorf("PythonPath = %q, want %q", cfg.PythonPath, "/usr/bin/python3")
		}
		if cfg.UseEmbeddedPython {
			t.Error("UseEmbeddedPython should be false when PYTHON_PATH is set")
		}
	})

	t.Run("USE_EMBEDDED_PYTHON=false", func(t *testing.T) {
		os.Unsetenv("PYTHON_PATH")
		os.Setenv("USE_EMBEDDED_PYTHON", "false")
		defer os.Unsetenv("USE_EMBEDDED_PYTHON")

		cfg := ConfigFromEnv()

		if cfg.UseEmbeddedPython {
			t.Error("UseEmbeddedPython should be false")
		}
	})

	t.Run("custom LOG_LEVEL", func(t *testing.T) {
		os.Setenv("LOG_LEVEL", "DEBUG")
		defer os.Unsetenv("LOG_LEVEL")

		cfg := ConfigFromEnv()

		if cfg.LogLevel != "DEBUG" {
			t.Errorf("LogLevel = %q, want %q", cfg.LogLevel, "DEBUG")
		}
	})

	t.Run("WATCH_ENABLED=false", func(t *testing.T) {
		os.Setenv("WATCH_ENABLED", "false")
		defer os.Unsetenv("WATCH_ENABLED")

		cfg := ConfigFromEnv()

		if cfg.WatchEnabled {
			t.Error("WatchEnabled should be false")
		}
	})
}

func TestGetEnvOrDefault(t *testing.T) {
	tests := []struct {
		name       string
		key        string
		defaultVal string
		envVal     string
		setEnv     bool
		expected   string
	}{
		{
			name:       "env not set returns default",
			key:        "TEST_NOT_SET_KEY",
			defaultVal: "default-value",
			setEnv:     false,
			expected:   "default-value",
		},
		{
			name:       "env set returns env value",
			key:        "TEST_SET_KEY",
			defaultVal: "default-value",
			envVal:     "env-value",
			setEnv:     true,
			expected:   "env-value",
		},
		{
			name:       "env set to empty returns default",
			key:        "TEST_EMPTY_KEY",
			defaultVal: "default-value",
			envVal:     "",
			setEnv:     true,
			expected:   "default-value",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Clean up
			os.Unsetenv(tt.key)

			if tt.setEnv {
				os.Setenv(tt.key, tt.envVal)
				defer os.Unsetenv(tt.key)
			}

			result := getEnvOrDefault(tt.key, tt.defaultVal)
			if result != tt.expected {
				t.Errorf("getEnvOrDefault(%q, %q) = %q, want %q",
					tt.key, tt.defaultVal, result, tt.expected)
			}
		})
	}
}

func TestEndpointInfo(t *testing.T) {
	info := EndpointInfo{
		Slug:        "test-endpoint",
		Name:        "Test Endpoint",
		Description: "A test endpoint",
		Type:        "model",
		Enabled:     true,
		Version:     "1.0.0",
	}

	if info.Slug != "test-endpoint" {
		t.Errorf("Slug = %q, want %q", info.Slug, "test-endpoint")
	}
	if info.Name != "Test Endpoint" {
		t.Errorf("Name = %q, want %q", info.Name, "Test Endpoint")
	}
	if info.Type != "model" {
		t.Errorf("Type = %q, want %q", info.Type, "model")
	}
}

func TestEndpointInfoHasPolicies(t *testing.T) {
	info := EndpointInfo{
		Slug: "test",
	}

	// Currently returns false (simplified check)
	if info.HasPolicies() {
		t.Error("HasPolicies should return false for base implementation")
	}
}

func TestSlogAdapterMethods(t *testing.T) {
	// Test that slogAdapter implements the required interface methods
	// Note: We can't easily test the actual logging without mocking slog.Logger
	// This is mainly a compile-time check that the adapter has the right methods

	// Just verify the struct exists and has the right methods
	var _ interface {
		Debug(msg string, args ...any)
		Info(msg string, args ...any)
		Warn(msg string, args ...any)
		Error(msg string, args ...any)
	} = (*slogAdapter)(nil)
}

// Helper to set or unset env var
func setEnvOrUnset(key, value string) {
	if value == "" {
		os.Unsetenv(key)
	} else {
		os.Setenv(key, value)
	}
}
