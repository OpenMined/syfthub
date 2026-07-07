package setupflow

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// LifecycleManager checks for expired setup steps and triggers refresh.
type LifecycleManager struct {
	engine *Engine
}

// NewLifecycleManager creates a lifecycle manager.
func NewLifecycleManager(engine *Engine) *LifecycleManager {
	return &LifecycleManager{engine: engine}
}

// RefreshResult reports the outcome of a refresh attempt.
type RefreshResult struct {
	Slug    string
	StepID  string
	Success bool
	Error   error
}

// CheckAndRefresh checks all endpoints for expired tokens and refreshes them.
// Called periodically by the daemon (e.g., every 5 minutes).
//
// For each endpoint with setup.yaml:
//  1. Read setup state
//  2. Find steps with expired tokens
//  3. If lifecycle.refresh is configured:
//     a. strategy=refresh_token: use refresh_token grant (no browser needed)
//     b. strategy=full_reauth: skip (requires user interaction)
//  4. Update .env and .setup-state.json
func (m *LifecycleManager) CheckAndRefresh(endpointsPath string) []RefreshResult {
	var results []RefreshResult

	entries, err := os.ReadDir(endpointsPath)
	if err != nil {
		return results
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		slug := entry.Name()
		endpointDir := filepath.Join(endpointsPath, slug)

		epResults := m.checkEndpoint(endpointDir, slug)
		results = append(results, epResults...)
	}

	return results
}

// checkEndpoint checks a single endpoint for expired tokens.
func (m *LifecycleManager) checkEndpoint(endpointDir, slug string) []RefreshResult {
	var results []RefreshResult

	// Check for setup.yaml
	setupPath := filepath.Join(endpointDir, "setup.yaml")
	spec, err := nodeops.ParseSetupYaml(setupPath)
	if err != nil || spec == nil {
		return results
	}

	// Check if lifecycle refresh is configured
	if spec.Lifecycle == nil || spec.Lifecycle.Refresh == nil {
		return results
	}

	refresh := spec.Lifecycle.Refresh

	// Only handle refresh_token strategy
	if refresh.Strategy != nodeops.StrategyRefreshToken {
		return results
	}

	// Read state
	state, err := nodeops.ReadSetupState(endpointDir)
	if err != nil || state == nil {
		return results
	}

	// Build step lookup
	stepMap := make(map[string]*nodeops.SetupStep)
	for i := range spec.Steps {
		stepMap[spec.Steps[i].ID] = &spec.Steps[i]
	}

	// Check each refresh step for expiry
	for _, stepID := range refresh.Steps {
		ss, ok := state.Steps[stepID]
		if !ok || ss.Status != nodeops.StepStatusCompleted {
			continue
		}

		// Check if expired
		if ss.ExpiresAt == "" {
			continue
		}

		expiresAt, err := time.Parse(time.RFC3339, ss.ExpiresAt)
		if err != nil {
			continue
		}

		// Refresh if expires within 5 minutes (proactive refresh)
		if time.Now().Add(5 * time.Minute).Before(expiresAt) {
			continue // Not yet expired or close to expiry
		}

		// Find the step config
		step, ok := stepMap[stepID]
		if !ok || step.OAuth2 == nil {
			continue
		}

		// Attempt refresh
		result := m.refreshToken(endpointDir, slug, stepID, step, state)
		results = append(results, result)
	}

	return results
}

// refreshToken performs a refresh_token grant for a single step.
func (m *LifecycleManager) refreshToken(endpointDir, slug, stepID string, step *nodeops.SetupStep, state *nodeops.SetupState) RefreshResult {
	result := RefreshResult{
		Slug:   slug,
		StepID: stepID,
	}

	// Read current .env to find refresh token and client credentials
	envPath := filepath.Join(endpointDir, ".env")
	envVars, err := nodeops.ReadEnvFile(envPath)
	if err != nil {
		result.Error = fmt.Errorf("failed to read .env: %w", err)
		return result
	}

	envMap := make(map[string]string)
	for _, ev := range envVars {
		envMap[ev.Key] = ev.Value
	}

	// Find refresh token — look for common env key patterns
	refreshToken := findRefreshToken(envMap, step)
	if refreshToken == "" {
		result.Error = fmt.Errorf("no refresh token found for step '%s'", stepID)
		return result
	}

	// Resolve client credentials
	clientID := step.OAuth2.ClientID
	if clientID == "" && step.OAuth2.ClientIDEnv != "" {
		clientID = envMap[step.OAuth2.ClientIDEnv]
	}
	clientSecret := step.OAuth2.ClientSecret
	if clientSecret == "" && step.OAuth2.ClientSecretEnv != "" {
		clientSecret = envMap[step.OAuth2.ClientSecretEnv]
	}

	// POST to token URL with refresh_token grant
	data := url.Values{
		"grant_type":    {"refresh_token"},
		"refresh_token": {refreshToken},
	}
	if clientID != "" {
		data.Set("client_id", clientID)
	}
	if clientSecret != "" {
		data.Set("client_secret", clientSecret)
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.PostForm(step.OAuth2.TokenURL, data)
	if err != nil {
		result.Error = fmt.Errorf("token refresh request failed: %w", err)
		return result
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20)) // 1MB limit
	if err != nil {
		result.Error = fmt.Errorf("failed to read refresh response: %w", err)
		return result
	}

	if resp.StatusCode != http.StatusOK {
		result.Error = fmt.Errorf("token refresh failed with status %d: %s", resp.StatusCode, string(body))
		return result
	}

	// Parse response
	var tokenResp map[string]any
	if err := json.Unmarshal(body, &tokenResp); err != nil {
		result.Error = fmt.Errorf("failed to parse refresh response: %w", err)
		return result
	}

	// Update .env with new tokens
	updates := make(map[string]string)

	// Map output templates to resolve new values
	if step.Outputs != nil {
		for envKey, tmpl := range step.Outputs {
			resolved := resolveRefreshTemplate(tmpl, tokenResp)
			if resolved != "" {
				updates[envKey] = resolved
			}
		}
	}

	// Also check env_key for single-value output
	if step.EnvKey != "" {
		if accessToken, ok := tokenResp["access_token"].(string); ok {
			updates[step.EnvKey] = accessToken
		}
	}

	if len(updates) > 0 {
		if err := mergeEnvFile(endpointDir, updates); err != nil {
			result.Error = fmt.Errorf("failed to update .env: %w", err)
			return result
		}
	}

	// Update state with new expiry
	expiresAt := ""
	if expiresIn, ok := tokenResp["expires_in"].(float64); ok && expiresIn > 0 {
		expiresAt = time.Now().Add(time.Duration(expiresIn) * time.Second).Format(time.RFC3339)
	}

	state.Steps[stepID] = nodeops.StepState{
		Status:      nodeops.StepStatusCompleted,
		CompletedAt: time.Now().Format(time.RFC3339),
		ExpiresAt:   expiresAt,
	}

	if err := nodeops.WriteSetupState(endpointDir, state); err != nil {
		result.Error = fmt.Errorf("failed to update setup state: %w", err)
		return result
	}

	result.Success = true
	return result
}

// findRefreshToken searches the env map for a refresh token value.
// It checks step outputs for keys containing "refresh_token" (case-insensitive),
// then falls back to common patterns.
func findRefreshToken(envMap map[string]string, step *nodeops.SetupStep) string {
	// First check step output keys for refresh token patterns
	if step.Outputs != nil {
		for envKey, tmpl := range step.Outputs {
			if strings.Contains(strings.ToLower(tmpl), "refresh_token") {
				if val, ok := envMap[envKey]; ok && val != "" {
					return val
				}
			}
		}
	}

	// Fall back to common refresh token env key patterns
	commonKeys := []string{
		"REFRESH_TOKEN",
		"GOOGLE_REFRESH_TOKEN",
		"SLACK_REFRESH_TOKEN",
		"GITHUB_REFRESH_TOKEN",
		"NOTION_REFRESH_TOKEN",
	}
	for _, key := range commonKeys {
		if val, ok := envMap[key]; ok && val != "" {
			return val
		}
	}

	// Last resort: any key containing "refresh_token" (case-insensitive)
	for key, val := range envMap {
		if strings.Contains(strings.ToLower(key), "refresh_token") && val != "" {
			return val
		}
	}

	return ""
}

// resolveRefreshTemplate resolves a simple output template like
// "{{response.access_token}}" against the token response JSON.
func resolveRefreshTemplate(tmpl string, data map[string]any) string {
	// Only handle {{response.X}} patterns
	if !strings.HasPrefix(tmpl, "{{response.") || !strings.HasSuffix(tmpl, "}}") {
		return ""
	}

	path := tmpl[len("{{response.") : len(tmpl)-2]
	parts := strings.Split(path, ".")

	var current any = data
	for _, part := range parts {
		m, ok := current.(map[string]any)
		if !ok {
			return ""
		}
		current, ok = m[part]
		if !ok {
			return ""
		}
	}

	switch v := current.(type) {
	case string:
		return v
	case float64:
		return fmt.Sprintf("%v", v)
	default:
		return fmt.Sprintf("%v", v)
	}
}
