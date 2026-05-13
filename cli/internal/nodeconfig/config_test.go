package nodeconfig

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultNodeConfig(t *testing.T) {
	cfg := DefaultNodeConfig()

	if cfg.HubURL != "https://syfthub.openmined.org" {
		t.Errorf("HubURL = %q, want %q", cfg.HubURL, "https://syfthub.openmined.org")
	}
	if cfg.Port != 8000 {
		t.Errorf("Port = %d, want 8000", cfg.Port)
	}
	if cfg.LogLevel != "INFO" {
		t.Errorf("LogLevel = %q, want %q", cfg.LogLevel, "INFO")
	}
	if cfg.Timeout != 30.0 {
		t.Errorf("Timeout = %f, want 30.0", cfg.Timeout)
	}
	if cfg.APIToken != "" {
		t.Errorf("APIToken should be empty by default, got %q", cfg.APIToken)
	}
	if cfg.IsConfigured {
		t.Error("IsConfigured should be false by default")
	}
	if cfg.ContainerEnabled {
		t.Error("ContainerEnabled should be false by default")
	}
	if cfg.ContainerRuntime != "" {
		t.Errorf("ContainerRuntime should be empty by default, got %q", cfg.ContainerRuntime)
	}
	if cfg.ContainerImage != "" {
		t.Errorf("ContainerImage should be empty by default, got %q", cfg.ContainerImage)
	}
	if cfg.EndpointsPath == "" {
		t.Error("EndpointsPath should not be empty")
	}

	// Default aggregator
	if cfg.DefaultAggregator != "default" {
		t.Errorf("DefaultAggregator = %q, want %q", cfg.DefaultAggregator, "default")
	}
	if agg, ok := cfg.Aggregators["default"]; !ok {
		t.Error("Aggregators map should contain 'default' key")
	} else if agg.URL != "https://syfthub.openmined.org/aggregator/api/v1" {
		t.Errorf("default aggregator URL = %q, want the default", agg.URL)
	}

	// Default accounting
	if cfg.DefaultAccounting != "default" {
		t.Errorf("DefaultAccounting = %q, want %q", cfg.DefaultAccounting, "default")
	}
	if acc, ok := cfg.AccountingServices["default"]; !ok {
		t.Error("AccountingServices map should contain 'default' key")
	} else if acc.URL != "https://syftaccounting.centralus.cloudapp.azure.com" {
		t.Errorf("default accounting URL = %q, want the default", acc.URL)
	}
}

func TestNodeConfig_JSONRoundTrip(t *testing.T) {
	cfg := &NodeConfig{
		HubURL:   "https://example.com",
		APIToken: "test-token-123",
		Aggregators: map[string]AggregatorConfig{
			"prod": {URL: "https://agg.example.com"},
		},
		AccountingServices: map[string]AccountingConfig{
			"prod": {URL: "https://acc.example.com"},
		},
		DefaultAggregator: "prod",
		DefaultAccounting: "prod",
		Timeout:           60.0,
		EndpointsPath:     "/tmp/endpoints",
		IsConfigured:      true,
		MarketplaceURL:    "https://market.example.com",
		LogLevel:          "DEBUG",
		PythonPath:        "/usr/bin/python3",
		Port:              9000,
		ContainerEnabled:  true,
		ContainerRuntime:  "docker",
		ContainerImage:    "syfthub/runner:v2",
	}

	data, err := json.Marshal(cfg)
	if err != nil {
		t.Fatalf("Marshal failed: %v", err)
	}

	// Verify snake_case JSON keys
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map failed: %v", err)
	}

	expectedKeys := []string{
		"hub_url", "api_token", "aggregators", "accounting_services",
		"default_aggregator", "default_accounting", "timeout",
		"endpoints_path", "is_configured", "marketplace_url",
		"log_level", "python_path", "port",
		"container_enabled", "container_runtime", "container_image",
	}
	for _, key := range expectedKeys {
		if _, ok := raw[key]; !ok {
			t.Errorf("expected JSON key %q not found in marshalled output", key)
		}
	}

	// Round-trip
	var restored NodeConfig
	if err := json.Unmarshal(data, &restored); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}

	if restored.HubURL != cfg.HubURL {
		t.Errorf("HubURL = %q, want %q", restored.HubURL, cfg.HubURL)
	}
	if restored.APIToken != cfg.APIToken {
		t.Errorf("APIToken = %q, want %q", restored.APIToken, cfg.APIToken)
	}
	if restored.Port != cfg.Port {
		t.Errorf("Port = %d, want %d", restored.Port, cfg.Port)
	}
	if restored.Timeout != cfg.Timeout {
		t.Errorf("Timeout = %f, want %f", restored.Timeout, cfg.Timeout)
	}
	if restored.ContainerEnabled != cfg.ContainerEnabled {
		t.Errorf("ContainerEnabled = %v, want %v", restored.ContainerEnabled, cfg.ContainerEnabled)
	}
	if restored.ContainerRuntime != cfg.ContainerRuntime {
		t.Errorf("ContainerRuntime = %q, want %q", restored.ContainerRuntime, cfg.ContainerRuntime)
	}
	if restored.ContainerImage != cfg.ContainerImage {
		t.Errorf("ContainerImage = %q, want %q", restored.ContainerImage, cfg.ContainerImage)
	}
	if restored.IsConfigured != cfg.IsConfigured {
		t.Errorf("IsConfigured = %v, want %v", restored.IsConfigured, cfg.IsConfigured)
	}
	if restored.MarketplaceURL != cfg.MarketplaceURL {
		t.Errorf("MarketplaceURL = %q, want %q", restored.MarketplaceURL, cfg.MarketplaceURL)
	}
	if restored.DefaultAggregator != cfg.DefaultAggregator {
		t.Errorf("DefaultAggregator = %q, want %q", restored.DefaultAggregator, cfg.DefaultAggregator)
	}
	if restored.DefaultAccounting != cfg.DefaultAccounting {
		t.Errorf("DefaultAccounting = %q, want %q", restored.DefaultAccounting, cfg.DefaultAccounting)
	}
}

func TestNodeConfig_Configured(t *testing.T) {
	tests := []struct {
		name         string
		isConfigured bool
		hubURL       string
		apiToken     string
		want         bool
	}{
		{
			name:         "all set",
			isConfigured: true,
			hubURL:       "https://example.com",
			apiToken:     "tok",
			want:         true,
		},
		{
			name:         "missing IsConfigured",
			isConfigured: false,
			hubURL:       "https://example.com",
			apiToken:     "tok",
			want:         false,
		},
		{
			name:         "missing HubURL",
			isConfigured: true,
			hubURL:       "",
			apiToken:     "tok",
			want:         false,
		},
		{
			name:         "missing APIToken",
			isConfigured: true,
			hubURL:       "https://example.com",
			apiToken:     "",
			want:         false,
		},
		{
			name:         "all empty",
			isConfigured: false,
			hubURL:       "",
			apiToken:     "",
			want:         false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &NodeConfig{
				IsConfigured: tt.isConfigured,
				HubURL:       tt.hubURL,
				APIToken:     tt.apiToken,
			}
			if got := cfg.Configured(); got != tt.want {
				t.Errorf("Configured() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestNodeConfig_HasAPIToken(t *testing.T) {
	cfg := &NodeConfig{}
	if cfg.HasAPIToken() {
		t.Error("HasAPIToken() should be false for empty token")
	}

	cfg.APIToken = "my-token"
	if !cfg.HasAPIToken() {
		t.Error("HasAPIToken() should be true after setting token")
	}
}

func TestNodeConfig_SetAPIToken(t *testing.T) {
	cfg := &NodeConfig{}
	cfg.SetAPIToken("new-token")
	if cfg.APIToken != "new-token" {
		t.Errorf("APIToken = %q, want %q", cfg.APIToken, "new-token")
	}
}

func TestNodeConfig_ClearAPIToken(t *testing.T) {
	cfg := &NodeConfig{APIToken: "existing-token"}
	cfg.ClearAPIToken()
	if cfg.APIToken != "" {
		t.Errorf("APIToken should be empty after ClearAPIToken, got %q", cfg.APIToken)
	}
	if cfg.HasAPIToken() {
		t.Error("HasAPIToken() should be false after ClearAPIToken")
	}
}

func TestNodeConfig_GetAggregatorURL(t *testing.T) {
	cfg := &NodeConfig{
		Aggregators: map[string]AggregatorConfig{
			"default": {URL: "https://default-agg.example.com"},
			"staging": {URL: "https://staging-agg.example.com"},
		},
		DefaultAggregator: "default",
	}

	tests := []struct {
		name  string
		alias string
		want  string
	}{
		{
			name:  "known alias",
			alias: "staging",
			want:  "https://staging-agg.example.com",
		},
		{
			name:  "default fallback (empty alias)",
			alias: "",
			want:  "https://default-agg.example.com",
		},
		{
			name:  "unknown alias treated as direct URL",
			alias: "https://custom-agg.example.com",
			want:  "https://custom-agg.example.com",
		},
		{
			name:  "unknown non-URL alias returned as-is",
			alias: "nonexistent",
			want:  "nonexistent",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := cfg.GetAggregatorURL(tt.alias)
			if got != tt.want {
				t.Errorf("GetAggregatorURL(%q) = %q, want %q", tt.alias, got, tt.want)
			}
		})
	}

	// Test with no default aggregator configured
	t.Run("empty default returns empty string", func(t *testing.T) {
		cfg2 := &NodeConfig{
			Aggregators:       map[string]AggregatorConfig{},
			DefaultAggregator: "",
		}
		got := cfg2.GetAggregatorURL("")
		if got != "" {
			t.Errorf("GetAggregatorURL(\"\") = %q, want empty string", got)
		}
	})

	// Test default alias not in map
	t.Run("default alias missing from map", func(t *testing.T) {
		cfg3 := &NodeConfig{
			Aggregators:       map[string]AggregatorConfig{},
			DefaultAggregator: "missing",
		}
		got := cfg3.GetAggregatorURL("")
		if got != "" {
			t.Errorf("GetAggregatorURL(\"\") = %q, want empty string when default alias not in map", got)
		}
	})
}

func TestNodeConfig_GetAccountingURL(t *testing.T) {
	cfg := &NodeConfig{
		AccountingServices: map[string]AccountingConfig{
			"default": {URL: "https://default-acc.example.com"},
			"staging": {URL: "https://staging-acc.example.com"},
		},
		DefaultAccounting: "default",
	}

	tests := []struct {
		name  string
		alias string
		want  string
	}{
		{
			name:  "known alias",
			alias: "staging",
			want:  "https://staging-acc.example.com",
		},
		{
			name:  "default fallback (empty alias)",
			alias: "",
			want:  "https://default-acc.example.com",
		},
		{
			name:  "unknown alias treated as direct URL",
			alias: "https://custom-acc.example.com",
			want:  "https://custom-acc.example.com",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := cfg.GetAccountingURL(tt.alias)
			if got != tt.want {
				t.Errorf("GetAccountingURL(%q) = %q, want %q", tt.alias, got, tt.want)
			}
		})
	}

	// Test with no default accounting configured
	t.Run("empty default returns empty string", func(t *testing.T) {
		cfg2 := &NodeConfig{
			AccountingServices: map[string]AccountingConfig{},
			DefaultAccounting:  "",
		}
		got := cfg2.GetAccountingURL("")
		if got != "" {
			t.Errorf("GetAccountingURL(\"\") = %q, want empty string", got)
		}
	})

	t.Run("default alias missing from map", func(t *testing.T) {
		cfg3 := &NodeConfig{
			AccountingServices: map[string]AccountingConfig{},
			DefaultAccounting:  "missing",
		}
		got := cfg3.GetAccountingURL("")
		if got != "" {
			t.Errorf("GetAccountingURL(\"\") = %q, want empty string when default alias not in map", got)
		}
	})
}

func TestNodeConfig_SaveAndLoad(t *testing.T) {
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "settings.json")

	original := &NodeConfig{
		HubURL:   "https://test-hub.example.com",
		APIToken: "syft_pat_testtoken123",
		Aggregators: map[string]AggregatorConfig{
			"default": {URL: "https://agg.example.com"},
			"local":   {URL: "http://localhost:8001"},
		},
		AccountingServices: map[string]AccountingConfig{
			"default": {URL: "https://acc.example.com"},
		},
		DefaultAggregator: "default",
		DefaultAccounting: "default",
		Timeout:           45.0,
		EndpointsPath:     "/opt/syfthub/endpoints",
		IsConfigured:      true,
		MarketplaceURL:    "https://market.example.com/manifest.json",
		LogLevel:          "DEBUG",
		PythonPath:        "/usr/bin/python3.11",
		Port:              9090,
		ContainerEnabled:  true,
		ContainerRuntime:  "podman",
		ContainerImage:    "syfthub/runner:v3",
	}

	if err := original.SaveTo(tmpFile); err != nil {
		t.Fatalf("SaveTo failed: %v", err)
	}

	loaded := LoadFrom(tmpFile)

	if loaded.HubURL != original.HubURL {
		t.Errorf("HubURL = %q, want %q", loaded.HubURL, original.HubURL)
	}
	if loaded.APIToken != original.APIToken {
		t.Errorf("APIToken = %q, want %q", loaded.APIToken, original.APIToken)
	}
	if loaded.Port != original.Port {
		t.Errorf("Port = %d, want %d", loaded.Port, original.Port)
	}
	if loaded.Timeout != original.Timeout {
		t.Errorf("Timeout = %f, want %f", loaded.Timeout, original.Timeout)
	}
	if loaded.IsConfigured != original.IsConfigured {
		t.Errorf("IsConfigured = %v, want %v", loaded.IsConfigured, original.IsConfigured)
	}
	if loaded.EndpointsPath != original.EndpointsPath {
		t.Errorf("EndpointsPath = %q, want %q", loaded.EndpointsPath, original.EndpointsPath)
	}
	if loaded.LogLevel != original.LogLevel {
		t.Errorf("LogLevel = %q, want %q", loaded.LogLevel, original.LogLevel)
	}
	if loaded.PythonPath != original.PythonPath {
		t.Errorf("PythonPath = %q, want %q", loaded.PythonPath, original.PythonPath)
	}
	if loaded.MarketplaceURL != original.MarketplaceURL {
		t.Errorf("MarketplaceURL = %q, want %q", loaded.MarketplaceURL, original.MarketplaceURL)
	}
	if loaded.ContainerEnabled != original.ContainerEnabled {
		t.Errorf("ContainerEnabled = %v, want %v", loaded.ContainerEnabled, original.ContainerEnabled)
	}
	if loaded.ContainerRuntime != original.ContainerRuntime {
		t.Errorf("ContainerRuntime = %q, want %q", loaded.ContainerRuntime, original.ContainerRuntime)
	}
	if loaded.ContainerImage != original.ContainerImage {
		t.Errorf("ContainerImage = %q, want %q", loaded.ContainerImage, original.ContainerImage)
	}
	if loaded.DefaultAggregator != original.DefaultAggregator {
		t.Errorf("DefaultAggregator = %q, want %q", loaded.DefaultAggregator, original.DefaultAggregator)
	}
	if loaded.DefaultAccounting != original.DefaultAccounting {
		t.Errorf("DefaultAccounting = %q, want %q", loaded.DefaultAccounting, original.DefaultAccounting)
	}

	// Verify aggregator map preserved
	if agg, ok := loaded.Aggregators["local"]; !ok {
		t.Error("Aggregators 'local' key missing after round-trip")
	} else if agg.URL != "http://localhost:8001" {
		t.Errorf("Aggregators['local'].URL = %q, want %q", agg.URL, "http://localhost:8001")
	}
}

func TestNodeConfig_ContainerFields(t *testing.T) {
	tests := []struct {
		name    string
		enabled bool
		runtime string
		image   string
	}{
		{"defaults (all empty)", false, "", ""},
		{"docker enabled", true, "docker", "syfthub/endpoint-runner:latest"},
		{"podman enabled", true, "podman", "custom-image:v1"},
		{"auto runtime", true, "auto", ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &NodeConfig{
				ContainerEnabled: tt.enabled,
				ContainerRuntime: tt.runtime,
				ContainerImage:   tt.image,
			}

			data, err := json.Marshal(cfg)
			if err != nil {
				t.Fatalf("Marshal failed: %v", err)
			}

			var restored NodeConfig
			if err := json.Unmarshal(data, &restored); err != nil {
				t.Fatalf("Unmarshal failed: %v", err)
			}

			if restored.ContainerEnabled != tt.enabled {
				t.Errorf("ContainerEnabled = %v, want %v", restored.ContainerEnabled, tt.enabled)
			}
			if restored.ContainerRuntime != tt.runtime {
				t.Errorf("ContainerRuntime = %q, want %q", restored.ContainerRuntime, tt.runtime)
			}
			if restored.ContainerImage != tt.image {
				t.Errorf("ContainerImage = %q, want %q", restored.ContainerImage, tt.image)
			}
		})
	}
}

func TestNodeConfig_AggregatorConfig(t *testing.T) {
	agg := AggregatorConfig{URL: "https://agg.example.com"}
	data, err := json.Marshal(agg)
	if err != nil {
		t.Fatalf("Marshal failed: %v", err)
	}

	var raw map[string]string
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map failed: %v", err)
	}
	if raw["url"] != "https://agg.example.com" {
		t.Errorf("JSON key should be 'url', got value %q", raw["url"])
	}

	var restored AggregatorConfig
	if err := json.Unmarshal(data, &restored); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}
	if restored.URL != agg.URL {
		t.Errorf("URL = %q, want %q", restored.URL, agg.URL)
	}
}

func TestNodeConfig_AccountingConfig(t *testing.T) {
	acc := AccountingConfig{URL: "https://acc.example.com"}
	data, err := json.Marshal(acc)
	if err != nil {
		t.Fatalf("Marshal failed: %v", err)
	}

	var raw map[string]string
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("Unmarshal to map failed: %v", err)
	}
	if raw["url"] != "https://acc.example.com" {
		t.Errorf("JSON key should be 'url', got value %q", raw["url"])
	}

	var restored AccountingConfig
	if err := json.Unmarshal(data, &restored); err != nil {
		t.Fatalf("Unmarshal failed: %v", err)
	}
	if restored.URL != acc.URL {
		t.Errorf("URL = %q, want %q", restored.URL, acc.URL)
	}
}

func TestNodeConfig_MarketplaceURL(t *testing.T) {
	tests := []struct {
		name           string
		marketplaceURL string
		hubURL         string
		want           string
	}{
		{
			name:           "explicit marketplace URL",
			marketplaceURL: "https://custom-market.example.com/manifest.json",
			hubURL:         "https://hub.example.com",
			want:           "https://custom-market.example.com/manifest.json",
		},
		{
			name:           "derived from hub URL",
			marketplaceURL: "",
			hubURL:         "https://syfthub.openmined.org",
			want:           "https://syfthub.openmined.org/marketplace/manifest.json",
		},
		{
			name:           "derived from hub URL with trailing slash",
			marketplaceURL: "",
			hubURL:         "https://syfthub.openmined.org/",
			want:           "https://syfthub.openmined.org/marketplace/manifest.json",
		},
		{
			name:           "both empty",
			marketplaceURL: "",
			hubURL:         "",
			want:           "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &NodeConfig{
				MarketplaceURL: tt.marketplaceURL,
				HubURL:         tt.hubURL,
			}
			got := cfg.GetMarketplaceURL()
			if got != tt.want {
				t.Errorf("GetMarketplaceURL() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestLoadFrom_NonexistentFile(t *testing.T) {
	cfg := LoadFrom("/nonexistent/path/settings.json")

	// Should return defaults
	if cfg.HubURL != "https://syfthub.openmined.org" {
		t.Errorf("HubURL = %q, want default", cfg.HubURL)
	}
	if cfg.Port != 8000 {
		t.Errorf("Port = %d, want 8000", cfg.Port)
	}
}

func TestLoadFrom_InvalidJSON(t *testing.T) {
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "settings.json")

	if err := os.WriteFile(tmpFile, []byte("not valid json {{{"), 0600); err != nil {
		t.Fatalf("WriteFile failed: %v", err)
	}

	cfg := LoadFrom(tmpFile)

	// Should return defaults on parse error
	if cfg.HubURL != "https://syfthub.openmined.org" {
		t.Errorf("HubURL = %q, want default", cfg.HubURL)
	}
}

func TestLoadFrom_PartialJSON(t *testing.T) {
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "settings.json")

	// Write partial config — only HubURL set
	partial := `{"hub_url": "https://custom.example.com", "api_token": "tok"}`
	if err := os.WriteFile(tmpFile, []byte(partial), 0600); err != nil {
		t.Fatalf("WriteFile failed: %v", err)
	}

	cfg := LoadFrom(tmpFile)

	if cfg.HubURL != "https://custom.example.com" {
		t.Errorf("HubURL = %q, want custom value", cfg.HubURL)
	}
	if cfg.APIToken != "tok" {
		t.Errorf("APIToken = %q, want %q", cfg.APIToken, "tok")
	}
	// Port should get the default since it was set on the base config
	if cfg.Port != 8000 {
		t.Errorf("Port = %d, want default 8000", cfg.Port)
	}
}

func TestSaveTo_CreatesDirectory(t *testing.T) {
	tmpDir := t.TempDir()
	nested := filepath.Join(tmpDir, "a", "b", "c", "settings.json")

	cfg := DefaultNodeConfig()
	if err := cfg.SaveTo(nested); err != nil {
		t.Fatalf("SaveTo should create parent directories, got: %v", err)
	}

	if _, err := os.Stat(nested); os.IsNotExist(err) {
		t.Error("settings file was not created")
	}
}

func TestSaveTo_FilePermissions(t *testing.T) {
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "settings.json")

	cfg := DefaultNodeConfig()
	cfg.APIToken = "secret-token"
	if err := cfg.SaveTo(tmpFile); err != nil {
		t.Fatalf("SaveTo failed: %v", err)
	}

	info, err := os.Stat(tmpFile)
	if err != nil {
		t.Fatalf("Stat failed: %v", err)
	}

	perm := info.Mode().Perm()
	if perm != 0600 {
		t.Errorf("file permissions = %o, want 0600", perm)
	}
}

func TestNodeConfig_NilMapsAfterUnmarshal(t *testing.T) {
	// Simulate loading a config that explicitly has null/missing maps
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "settings.json")

	content := `{"hub_url": "https://example.com", "aggregators": null, "accounting_services": null}`
	if err := os.WriteFile(tmpFile, []byte(content), 0600); err != nil {
		t.Fatalf("WriteFile failed: %v", err)
	}

	cfg := LoadFrom(tmpFile)

	// LoadFrom should ensure maps are initialized
	if cfg.Aggregators == nil {
		t.Error("Aggregators should not be nil after LoadFrom")
	}
	if cfg.AccountingServices == nil {
		t.Error("AccountingServices should not be nil after LoadFrom")
	}
}
