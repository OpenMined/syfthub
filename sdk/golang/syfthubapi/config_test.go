package syfthubapi

import (
	"errors"
	"testing"
	"time"
)

func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()

	tests := []struct {
		name     string
		got      any
		expected any
	}{
		{"LogLevel", cfg.LogLevel, "INFO"},
		{"ServerHost", cfg.ServerHost, "0.0.0.0"},
		{"ServerPort", cfg.ServerPort, 8000},
		{"HeartbeatEnabled", cfg.HeartbeatEnabled, true},
		{"HeartbeatTTLSeconds", cfg.HeartbeatTTLSeconds, 300},
		{"HeartbeatIntervalMultiplier", cfg.HeartbeatIntervalMultiplier, 0.8},
		{"WatchEnabled", cfg.WatchEnabled, true},
		{"WatchDebounceSeconds", cfg.WatchDebounceSeconds, 1.0},
		{"PythonPath", cfg.PythonPath, "python3"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.expected {
				t.Errorf("DefaultConfig().%s = %v, want %v", tt.name, tt.got, tt.expected)
			}
		})
	}

	// Required fields should be empty by default
	if cfg.SyftHubURL != "" {
		t.Errorf("SyftHubURL should be empty, got %q", cfg.SyftHubURL)
	}
	if cfg.APIKey != "" {
		t.Errorf("APIKey should be empty, got %q", cfg.APIKey)
	}
	if cfg.SpaceURL != "" {
		t.Errorf("SpaceURL should be empty, got %q", cfg.SpaceURL)
	}
}

func TestConfigLoadFromEnv(t *testing.T) {
	t.Run("loads all environment variables", func(t *testing.T) {
		// Set environment variables
		t.Setenv("SYFTHUB_URL", "https://hub.example.com")
		t.Setenv("SYFTHUB_API_KEY", "test-api-key")
		t.Setenv("SPACE_URL", "https://space.example.com")
		t.Setenv("LOG_LEVEL", "debug")
		t.Setenv("SERVER_HOST", "127.0.0.1")
		t.Setenv("SERVER_PORT", "9000")
		t.Setenv("HEARTBEAT_ENABLED", "false")
		t.Setenv("HEARTBEAT_TTL_SECONDS", "600")
		t.Setenv("HEARTBEAT_INTERVAL_MULTIPLIER", "0.5")
		t.Setenv("ENDPOINTS_PATH", "/custom/endpoints")
		t.Setenv("WATCH_ENABLED", "false")
		t.Setenv("WATCH_DEBOUNCE_SECONDS", "2.5")
		t.Setenv("PYTHON_PATH", "/usr/bin/python3.11")

		cfg := DefaultConfig()
		err := cfg.LoadFromEnv()
		if err != nil {
			t.Fatalf("LoadFromEnv() error = %v", err)
		}

		if cfg.SyftHubURL != "https://hub.example.com" {
			t.Errorf("SyftHubURL = %q, want %q", cfg.SyftHubURL, "https://hub.example.com")
		}
		if cfg.APIKey != "test-api-key" {
			t.Errorf("APIKey = %q, want %q", cfg.APIKey, "test-api-key")
		}
		if cfg.SpaceURL != "https://space.example.com" {
			t.Errorf("SpaceURL = %q, want %q", cfg.SpaceURL, "https://space.example.com")
		}
		if cfg.LogLevel != "DEBUG" {
			t.Errorf("LogLevel = %q, want %q", cfg.LogLevel, "DEBUG")
		}
		if cfg.ServerHost != "127.0.0.1" {
			t.Errorf("ServerHost = %q, want %q", cfg.ServerHost, "127.0.0.1")
		}
		if cfg.ServerPort != 9000 {
			t.Errorf("ServerPort = %d, want %d", cfg.ServerPort, 9000)
		}
		if cfg.HeartbeatEnabled {
			t.Error("HeartbeatEnabled should be false")
		}
		if cfg.HeartbeatTTLSeconds != 600 {
			t.Errorf("HeartbeatTTLSeconds = %d, want %d", cfg.HeartbeatTTLSeconds, 600)
		}
		if cfg.HeartbeatIntervalMultiplier != 0.5 {
			t.Errorf("HeartbeatIntervalMultiplier = %f, want %f", cfg.HeartbeatIntervalMultiplier, 0.5)
		}
		if cfg.EndpointsPath != "/custom/endpoints" {
			t.Errorf("EndpointsPath = %q, want %q", cfg.EndpointsPath, "/custom/endpoints")
		}
		if cfg.WatchEnabled {
			t.Error("WatchEnabled should be false")
		}
		if cfg.WatchDebounceSeconds != 2.5 {
			t.Errorf("WatchDebounceSeconds = %f, want %f", cfg.WatchDebounceSeconds, 2.5)
		}
		if cfg.PythonPath != "/usr/bin/python3.11" {
			t.Errorf("PythonPath = %q, want %q", cfg.PythonPath, "/usr/bin/python3.11")
		}
	})

	t.Run("invalid SERVER_PORT", func(t *testing.T) {
		t.Setenv("SERVER_PORT", "not-a-number")

		cfg := DefaultConfig()
		err := cfg.LoadFromEnv()
		if err == nil {
			t.Error("expected error for invalid SERVER_PORT")
		}
	})

	t.Run("invalid HEARTBEAT_TTL_SECONDS", func(t *testing.T) {
		t.Setenv("HEARTBEAT_TTL_SECONDS", "invalid")

		cfg := DefaultConfig()
		err := cfg.LoadFromEnv()
		if err == nil {
			t.Error("expected error for invalid HEARTBEAT_TTL_SECONDS")
		}
	})

	t.Run("invalid HEARTBEAT_INTERVAL_MULTIPLIER", func(t *testing.T) {
		t.Setenv("HEARTBEAT_INTERVAL_MULTIPLIER", "not-float")

		cfg := DefaultConfig()
		err := cfg.LoadFromEnv()
		if err == nil {
			t.Error("expected error for invalid HEARTBEAT_INTERVAL_MULTIPLIER")
		}
	})

	t.Run("invalid WATCH_DEBOUNCE_SECONDS", func(t *testing.T) {
		t.Setenv("WATCH_DEBOUNCE_SECONDS", "xyz")

		cfg := DefaultConfig()
		err := cfg.LoadFromEnv()
		if err == nil {
			t.Error("expected error for invalid WATCH_DEBOUNCE_SECONDS")
		}
	})

	t.Run("empty environment preserves defaults", func(t *testing.T) {
		cfg := DefaultConfig()
		err := cfg.LoadFromEnv()
		if err != nil {
			t.Fatalf("LoadFromEnv() error = %v", err)
		}

		// Defaults should be preserved
		if cfg.ServerPort != 8000 {
			t.Errorf("ServerPort should preserve default, got %d", cfg.ServerPort)
		}
	})
}

func TestConfigValidate(t *testing.T) {
	validConfig := func() *Config {
		return &Config{
			SyftHubURL:                  "https://hub.example.com",
			APIKey:                      "test-api-key",
			SpaceURL:                    "https://space.example.com",
			LogLevel:                    "INFO",
			HeartbeatTTLSeconds:         300,
			HeartbeatIntervalMultiplier: 0.8,
		}
	}

	t.Run("valid config", func(t *testing.T) {
		cfg := validConfig()
		if err := cfg.Validate(); err != nil {
			t.Errorf("Validate() error = %v", err)
		}
	})

	t.Run("missing SyftHubURL", func(t *testing.T) {
		cfg := validConfig()
		cfg.SyftHubURL = ""
		err := cfg.Validate()
		if err == nil {
			t.Error("expected error for missing SyftHubURL")
		}
		if !errors.Is(err, ErrConfiguration) {
			t.Error("expected ConfigurationError")
		}
	})

	t.Run("missing APIKey", func(t *testing.T) {
		cfg := validConfig()
		cfg.APIKey = ""
		err := cfg.Validate()
		if err == nil {
			t.Error("expected error for missing APIKey")
		}
	})

	t.Run("missing SpaceURL", func(t *testing.T) {
		cfg := validConfig()
		cfg.SpaceURL = ""
		err := cfg.Validate()
		if err == nil {
			t.Error("expected error for missing SpaceURL")
		}
	})

	t.Run("invalid SpaceURL format", func(t *testing.T) {
		cfg := validConfig()
		cfg.SpaceURL = "invalid-url"
		err := cfg.Validate()
		if err == nil {
			t.Error("expected error for invalid SpaceURL format")
		}
	})

	t.Run("valid SpaceURL formats", func(t *testing.T) {
		validURLs := []string{
			"http://localhost:8000",
			"https://space.example.com",
			"tunneling:testuser",
		}

		for _, url := range validURLs {
			cfg := validConfig()
			cfg.SpaceURL = url
			if err := cfg.Validate(); err != nil {
				t.Errorf("SpaceURL %q should be valid, got error: %v", url, err)
			}
		}
	})

	t.Run("invalid log level", func(t *testing.T) {
		cfg := validConfig()
		cfg.LogLevel = "INVALID"
		err := cfg.Validate()
		if err == nil {
			t.Error("expected error for invalid LogLevel")
		}
	})

	t.Run("valid log levels", func(t *testing.T) {
		validLevels := []string{"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "debug", "info", "warning", "warn", "error"}

		for _, level := range validLevels {
			cfg := validConfig()
			cfg.LogLevel = level
			if err := cfg.Validate(); err != nil {
				t.Errorf("LogLevel %q should be valid, got error: %v", level, err)
			}
		}
	})

	t.Run("HeartbeatTTLSeconds out of range", func(t *testing.T) {
		tests := []struct {
			name string
			ttl  int
		}{
			{"zero", 0},
			{"negative", -1},
			{"too large", 3601},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				cfg := validConfig()
				cfg.HeartbeatTTLSeconds = tt.ttl
				err := cfg.Validate()
				if err == nil {
					t.Errorf("expected error for HeartbeatTTLSeconds = %d", tt.ttl)
				}
			})
		}
	})

	t.Run("HeartbeatIntervalMultiplier out of range", func(t *testing.T) {
		tests := []struct {
			name string
			mult float64
		}{
			{"zero", 0.0},
			{"negative", -0.5},
			{"greater than 1", 1.5},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				cfg := validConfig()
				cfg.HeartbeatIntervalMultiplier = tt.mult
				err := cfg.Validate()
				if err == nil {
					t.Errorf("expected error for HeartbeatIntervalMultiplier = %f", tt.mult)
				}
			})
		}

		// 1.0 is a valid boundary (0 < value <= 1)
		t.Run("exactly 1 is valid", func(t *testing.T) {
			cfg := validConfig()
			cfg.HeartbeatIntervalMultiplier = 1.0
			err := cfg.Validate()
			if err != nil {
				t.Errorf("1.0 should be valid: %v", err)
			}
		})
	})
}

func TestConfigIsTunnelMode(t *testing.T) {
	tests := []struct {
		spaceURL string
		expected bool
	}{
		{"tunneling:testuser", true},
		{"tunneling:", true},
		{"https://space.example.com", false},
		{"http://localhost:8000", false},
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.spaceURL, func(t *testing.T) {
			cfg := &Config{SpaceURL: tt.spaceURL}
			if got := cfg.IsTunnelMode(); got != tt.expected {
				t.Errorf("IsTunnelMode() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func TestConfigGetTunnelUsername(t *testing.T) {
	tests := []struct {
		spaceURL string
		expected string
	}{
		{"tunneling:testuser", "testuser"},
		{"tunneling:user-with-dashes", "user-with-dashes"},
		{"tunneling:", ""},
		{"https://space.example.com", ""},
		{"http://localhost:8000", ""},
	}

	for _, tt := range tests {
		t.Run(tt.spaceURL, func(t *testing.T) {
			cfg := &Config{SpaceURL: tt.spaceURL}
			if got := cfg.GetTunnelUsername(); got != tt.expected {
				t.Errorf("GetTunnelUsername() = %q, want %q", got, tt.expected)
			}
		})
	}
}

func TestConfigHeartbeatInterval(t *testing.T) {
	tests := []struct {
		ttl      int
		mult     float64
		expected time.Duration
	}{
		{300, 0.8, 240 * time.Second},
		{100, 0.5, 50 * time.Second},
		{60, 1.0, 60 * time.Second},
		{10, 0.1, 1 * time.Second},
	}

	for _, tt := range tests {
		cfg := &Config{
			HeartbeatTTLSeconds:         tt.ttl,
			HeartbeatIntervalMultiplier: tt.mult,
		}
		got := cfg.HeartbeatInterval()
		if got != tt.expected {
			t.Errorf("HeartbeatInterval() with ttl=%d, mult=%f = %v, want %v",
				tt.ttl, tt.mult, got, tt.expected)
		}
	}
}

func TestConfigWatchDebounce(t *testing.T) {
	tests := []struct {
		seconds  float64
		expected time.Duration
	}{
		{1.0, 1 * time.Second},
		{0.5, 500 * time.Millisecond},
		{2.5, 2500 * time.Millisecond},
		{0.0, 0},
	}

	for _, tt := range tests {
		cfg := &Config{WatchDebounceSeconds: tt.seconds}
		got := cfg.WatchDebounce()
		if got != tt.expected {
			t.Errorf("WatchDebounce() with seconds=%f = %v, want %v",
				tt.seconds, got, tt.expected)
		}
	}
}

func TestDeriveNATSWebSocketURL(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		expected  string
		wantError bool
	}{
		{
			name:     "https with port",
			input:    "https://hub.example.com:443",
			expected: "wss://hub.example.com:443",
		},
		{
			name:     "https without port",
			input:    "https://hub.example.com",
			expected: "wss://hub.example.com:443",
		},
		{
			name:     "https with trailing slash",
			input:    "https://hub.example.com/",
			expected: "wss://hub.example.com:443",
		},
		{
			name:     "http with port",
			input:    "http://localhost:8000",
			expected: "ws://localhost:8000",
		},
		{
			name:     "http without port",
			input:    "http://localhost",
			expected: "ws://localhost:80",
		},
		{
			name:     "http with trailing slash",
			input:    "http://localhost/",
			expected: "ws://localhost:80",
		},
		{
			name:      "invalid scheme",
			input:     "ftp://example.com",
			wantError: true,
		},
		{
			name:      "no scheme",
			input:     "example.com",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := DeriveNATSWebSocketURL(tt.input)
			if tt.wantError {
				if err == nil {
					t.Errorf("expected error, got %q", got)
				}
			} else {
				if err != nil {
					t.Errorf("unexpected error: %v", err)
				}
				if got != tt.expected {
					t.Errorf("DeriveNATSWebSocketURL(%q) = %q, want %q", tt.input, got, tt.expected)
				}
			}
		})
	}
}

func TestOptionFunctions(t *testing.T) {
	t.Run("WithSyftHubURL", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithSyftHubURL("https://test.com")
		opt(cfg)
		if cfg.SyftHubURL != "https://test.com" {
			t.Errorf("expected %q, got %q", "https://test.com", cfg.SyftHubURL)
		}
	})

	t.Run("WithAPIKey", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithAPIKey("my-api-key")
		opt(cfg)
		if cfg.APIKey != "my-api-key" {
			t.Errorf("expected %q, got %q", "my-api-key", cfg.APIKey)
		}
	})

	t.Run("WithSpaceURL", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithSpaceURL("https://space.test.com")
		opt(cfg)
		if cfg.SpaceURL != "https://space.test.com" {
			t.Errorf("expected %q, got %q", "https://space.test.com", cfg.SpaceURL)
		}
	})

	t.Run("WithLogLevel", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithLogLevel("DEBUG")
		opt(cfg)
		if cfg.LogLevel != "DEBUG" {
			t.Errorf("expected %q, got %q", "DEBUG", cfg.LogLevel)
		}
	})

	t.Run("WithServerHost", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithServerHost("127.0.0.1")
		opt(cfg)
		if cfg.ServerHost != "127.0.0.1" {
			t.Errorf("expected %q, got %q", "127.0.0.1", cfg.ServerHost)
		}
	})

	t.Run("WithServerPort", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithServerPort(9000)
		opt(cfg)
		if cfg.ServerPort != 9000 {
			t.Errorf("expected %d, got %d", 9000, cfg.ServerPort)
		}
	})

	t.Run("WithHeartbeatEnabled", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithHeartbeatEnabled(false)
		opt(cfg)
		if cfg.HeartbeatEnabled {
			t.Error("expected false")
		}
	})

	t.Run("WithHeartbeatTTL", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithHeartbeatTTL(600)
		opt(cfg)
		if cfg.HeartbeatTTLSeconds != 600 {
			t.Errorf("expected %d, got %d", 600, cfg.HeartbeatTTLSeconds)
		}
	})

	t.Run("WithHeartbeatIntervalMultiplier", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithHeartbeatIntervalMultiplier(0.5)
		opt(cfg)
		if cfg.HeartbeatIntervalMultiplier != 0.5 {
			t.Errorf("expected %f, got %f", 0.5, cfg.HeartbeatIntervalMultiplier)
		}
	})

	t.Run("WithEndpointsPath", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithEndpointsPath("/custom/path")
		opt(cfg)
		if cfg.EndpointsPath != "/custom/path" {
			t.Errorf("expected %q, got %q", "/custom/path", cfg.EndpointsPath)
		}
	})

	t.Run("WithWatchEnabled", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithWatchEnabled(false)
		opt(cfg)
		if cfg.WatchEnabled {
			t.Error("expected false")
		}
	})

	t.Run("WithWatchDebounce", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithWatchDebounce(2.5)
		opt(cfg)
		if cfg.WatchDebounceSeconds != 2.5 {
			t.Errorf("expected %f, got %f", 2.5, cfg.WatchDebounceSeconds)
		}
	})

	t.Run("WithPythonPath", func(t *testing.T) {
		cfg := DefaultConfig()
		opt := WithPythonPath("/usr/bin/python3.11")
		opt(cfg)
		if cfg.PythonPath != "/usr/bin/python3.11" {
			t.Errorf("expected %q, got %q", "/usr/bin/python3.11", cfg.PythonPath)
		}
	})
}

func TestOptionChaining(t *testing.T) {
	cfg := DefaultConfig()
	options := []Option{
		WithSyftHubURL("https://hub.test.com"),
		WithAPIKey("test-key"),
		WithSpaceURL("tunneling:testuser"),
		WithLogLevel("DEBUG"),
		WithServerPort(9000),
	}

	for _, opt := range options {
		opt(cfg)
	}

	if cfg.SyftHubURL != "https://hub.test.com" {
		t.Errorf("SyftHubURL not set correctly")
	}
	if cfg.APIKey != "test-key" {
		t.Errorf("APIKey not set correctly")
	}
	if cfg.SpaceURL != "tunneling:testuser" {
		t.Errorf("SpaceURL not set correctly")
	}
	if cfg.LogLevel != "DEBUG" {
		t.Errorf("LogLevel not set correctly")
	}
	if cfg.ServerPort != 9000 {
		t.Errorf("ServerPort not set correctly")
	}
}
