package main

import (
	"encoding/json"
	"testing"
)

// ============================================================================
// AppState Tests
// ============================================================================

func TestAppStateConstants(t *testing.T) {
	tests := []struct {
		state    AppState
		expected string
	}{
		{StateIdle, "idle"},
		{StateStarting, "starting"},
		{StateRunning, "running"},
		{StateStopping, "stopping"},
		{StateError, "error"},
	}

	for _, tt := range tests {
		if string(tt.state) != tt.expected {
			t.Errorf("AppState %v = %q, want %q", tt.state, string(tt.state), tt.expected)
		}
	}
}

// ============================================================================
// StatusInfo Tests
// ============================================================================

func TestStatusInfoJSON(t *testing.T) {
	info := StatusInfo{
		State:        StateRunning,
		ErrorMessage: "",
		Mode:         "HTTP",
		Uptime:       3600,
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal error: %v", err)
	}

	if decoded["state"] != "running" {
		t.Errorf("state = %v, want %q", decoded["state"], "running")
	}
	if decoded["mode"] != "HTTP" {
		t.Errorf("mode = %v, want %q", decoded["mode"], "HTTP")
	}
	if decoded["uptime"].(float64) != 3600 {
		t.Errorf("uptime = %v, want 3600", decoded["uptime"])
	}
}

func TestStatusInfoJSONOmitEmpty(t *testing.T) {
	info := StatusInfo{
		State: StateIdle,
		Mode:  "HTTP",
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	// ErrorMessage should be omitted
	if _, ok := decoded["errorMessage"]; ok {
		t.Error("errorMessage should be omitted when empty")
	}
}

// ============================================================================
// EndpointInfo Tests
// ============================================================================

func TestEndpointInfoJSON(t *testing.T) {
	info := EndpointInfo{
		Slug:        "my-model",
		Name:        "My Model",
		Description: "A test model",
		Type:        "model",
		Enabled:     true,
		Version:     "1.0.0",
		HasPolicies: true,
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["slug"] != "my-model" {
		t.Errorf("slug = %v, want %q", decoded["slug"], "my-model")
	}
	if decoded["type"] != "model" {
		t.Errorf("type = %v, want %q", decoded["type"], "model")
	}
	if decoded["enabled"] != true {
		t.Errorf("enabled = %v, want true", decoded["enabled"])
	}
	if decoded["hasPolicies"] != true {
		t.Errorf("hasPolicies = %v, want true", decoded["hasPolicies"])
	}
}

// ============================================================================
// ConfigInfo Tests
// ============================================================================

func TestConfigInfoJSON(t *testing.T) {
	info := ConfigInfo{
		SyftHubURL:        "https://syfthub.example.com",
		SpaceURL:          "tunneling:user",
		EndpointsPath:     "/path/to/endpoints",
		LogLevel:          "DEBUG",
		WatchEnabled:      true,
		UseEmbeddedPython: false,
		PythonPath:        "/usr/bin/python3",
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["syfthubUrl"] != "https://syfthub.example.com" {
		t.Errorf("syfthubUrl = %v", decoded["syfthubUrl"])
	}
	if decoded["spaceUrl"] != "tunneling:user" {
		t.Errorf("spaceUrl = %v", decoded["spaceUrl"])
	}
}

// ============================================================================
// ConfigRequest Tests
// ============================================================================

func TestConfigRequestJSON(t *testing.T) {
	watchEnabled := true
	req := ConfigRequest{
		SyftHubURL:   "https://new.syfthub.com",
		APIKey:       "secret-key",
		WatchEnabled: &watchEnabled,
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["syfthubUrl"] != "https://new.syfthub.com" {
		t.Errorf("syfthubUrl = %v", decoded["syfthubUrl"])
	}
	if decoded["apiKey"] != "secret-key" {
		t.Errorf("apiKey = %v", decoded["apiKey"])
	}
}

// ============================================================================
// LogEntry Tests
// ============================================================================

func TestLogEntryJSON(t *testing.T) {
	entry := LogEntry{
		Timestamp: "2024-01-15T10:30:00Z",
		Level:     "INFO",
		Message:   "Test message",
		Fields:    `{"key":"value"}`,
	}

	data, err := json.Marshal(entry)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["timestamp"] != "2024-01-15T10:30:00Z" {
		t.Errorf("timestamp = %v", decoded["timestamp"])
	}
	if decoded["level"] != "INFO" {
		t.Errorf("level = %v", decoded["level"])
	}
	if decoded["message"] != "Test message" {
		t.Errorf("message = %v", decoded["message"])
	}
}

// ============================================================================
// RequestLogEntry Tests
// ============================================================================

func TestRequestLogEntryJSON(t *testing.T) {
	entry := RequestLogEntry{
		ID:            "log-123",
		Timestamp:     "2024-01-15T10:30:00Z",
		CorrelationID: "corr-456",
		EndpointSlug:  "my-model",
		EndpointType:  "model",
		User: &LogUserInfo{
			ID:       "user-1",
			Username: "testuser",
			Email:    "test@example.com",
		},
		Request: &LogRequestInfo{
			Type:    "chat",
			Query:   "Hello",
			RawSize: 100,
		},
		Response: &LogResponseInfo{
			Success: true,
			Content: "Hi there!",
		},
	}

	data, err := json.Marshal(entry)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["id"] != "log-123" {
		t.Errorf("id = %v", decoded["id"])
	}
	if decoded["correlationId"] != "corr-456" {
		t.Errorf("correlationId = %v", decoded["correlationId"])
	}
	if decoded["endpointSlug"] != "my-model" {
		t.Errorf("endpointSlug = %v", decoded["endpointSlug"])
	}

	// Check nested objects
	user := decoded["user"].(map[string]interface{})
	if user["username"] != "testuser" {
		t.Errorf("user.username = %v", user["username"])
	}

	response := decoded["response"].(map[string]interface{})
	if response["success"] != true {
		t.Errorf("response.success = %v", response["success"])
	}
}

// ============================================================================
// LogUserInfo Tests
// ============================================================================

func TestLogUserInfoJSON(t *testing.T) {
	info := LogUserInfo{
		ID:       "user-123",
		Username: "johndoe",
		Email:    "john@example.com",
		Role:     "admin",
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["id"] != "user-123" {
		t.Errorf("id = %v", decoded["id"])
	}
	if decoded["role"] != "admin" {
		t.Errorf("role = %v", decoded["role"])
	}
}

// ============================================================================
// LogMessage Tests
// ============================================================================

func TestLogMessageJSON(t *testing.T) {
	msg := LogMessage{
		Role:    "user",
		Content: "Hello, how are you?",
	}

	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["role"] != "user" {
		t.Errorf("role = %v", decoded["role"])
	}
	if decoded["content"] != "Hello, how are you?" {
		t.Errorf("content = %v", decoded["content"])
	}
}

// ============================================================================
// LogRequestInfo Tests
// ============================================================================

func TestLogRequestInfoJSON(t *testing.T) {
	info := LogRequestInfo{
		Type: "chat",
		Messages: []LogMessage{
			{Role: "user", Content: "Hi"},
			{Role: "assistant", Content: "Hello!"},
		},
		Query:   "search query",
		RawSize: 256,
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["type"] != "chat" {
		t.Errorf("type = %v", decoded["type"])
	}
	if decoded["rawSize"].(float64) != 256 {
		t.Errorf("rawSize = %v", decoded["rawSize"])
	}

	messages := decoded["messages"].([]interface{})
	if len(messages) != 2 {
		t.Errorf("len(messages) = %d, want 2", len(messages))
	}
}

// ============================================================================
// LogResponseInfo Tests
// ============================================================================

func TestLogResponseInfoJSON(t *testing.T) {
	info := LogResponseInfo{
		Success:          false,
		Content:          "",
		ContentTruncated: false,
		Error:            "Connection timeout",
		ErrorType:        "NetworkError",
		ErrorCode:        "TIMEOUT",
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["success"] != false {
		t.Errorf("success = %v", decoded["success"])
	}
	if decoded["error"] != "Connection timeout" {
		t.Errorf("error = %v", decoded["error"])
	}
	if decoded["errorType"] != "NetworkError" {
		t.Errorf("errorType = %v", decoded["errorType"])
	}
}

// ============================================================================
// LogPolicyInfo Tests
// ============================================================================

func TestLogPolicyInfoJSON(t *testing.T) {
	info := LogPolicyInfo{
		Evaluated:  true,
		Allowed:    false,
		PolicyName: "rate-limit",
		Reason:     "Rate limit exceeded",
		Pending:    false,
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["evaluated"] != true {
		t.Errorf("evaluated = %v", decoded["evaluated"])
	}
	if decoded["allowed"] != false {
		t.Errorf("allowed = %v", decoded["allowed"])
	}
	if decoded["policyName"] != "rate-limit" {
		t.Errorf("policyName = %v", decoded["policyName"])
	}
}

// ============================================================================
// LogTimingInfo Tests
// ============================================================================

func TestLogTimingInfoJSON(t *testing.T) {
	info := LogTimingInfo{
		ReceivedAt:  "2024-01-15T10:30:00.000Z",
		ProcessedAt: "2024-01-15T10:30:00.150Z",
		DurationMs:  150,
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["durationMs"].(float64) != 150 {
		t.Errorf("durationMs = %v", decoded["durationMs"])
	}
}

// ============================================================================
// LogQueryResult Tests
// ============================================================================

func TestLogQueryResultJSON(t *testing.T) {
	result := LogQueryResult{
		Logs: []RequestLogEntry{
			{ID: "log-1", EndpointSlug: "ep-1"},
			{ID: "log-2", EndpointSlug: "ep-1"},
		},
		Total:   100,
		HasMore: true,
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["total"].(float64) != 100 {
		t.Errorf("total = %v", decoded["total"])
	}
	if decoded["hasMore"] != true {
		t.Errorf("hasMore = %v", decoded["hasMore"])
	}

	logs := decoded["logs"].([]interface{})
	if len(logs) != 2 {
		t.Errorf("len(logs) = %d, want 2", len(logs))
	}
}

// ============================================================================
// LogStats Tests
// ============================================================================

func TestLogStatsJSON(t *testing.T) {
	lastTime := "2024-01-15T10:30:00Z"
	stats := LogStats{
		TotalRequests:   1000,
		SuccessCount:    950,
		ErrorCount:      40,
		PolicyDenyCount: 10,
		AvgDurationMs:   125.5,
		LastRequestTime: &lastTime,
	}

	data, err := json.Marshal(stats)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	if decoded["totalRequests"].(float64) != 1000 {
		t.Errorf("totalRequests = %v", decoded["totalRequests"])
	}
	if decoded["successCount"].(float64) != 950 {
		t.Errorf("successCount = %v", decoded["successCount"])
	}
	if decoded["avgDurationMs"].(float64) != 125.5 {
		t.Errorf("avgDurationMs = %v", decoded["avgDurationMs"])
	}
}

func TestLogStatsJSONNilLastRequestTime(t *testing.T) {
	stats := LogStats{
		TotalRequests: 0,
	}

	data, err := json.Marshal(stats)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	json.Unmarshal(data, &decoded)

	// lastRequestTime should be null/omitted
	if decoded["lastRequestTime"] != nil {
		t.Errorf("lastRequestTime should be nil, got %v", decoded["lastRequestTime"])
	}
}
