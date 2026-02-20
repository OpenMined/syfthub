package main

import (
	"os"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestNewApp(t *testing.T) {
	app := NewApp()

	if app == nil {
		t.Fatal("NewApp returned nil")
	}
	if app.state != StateIdle {
		t.Errorf("state = %v, want %v", app.state, StateIdle)
	}
	if app.runDone == nil {
		t.Error("runDone channel should be initialized")
	}
}

func TestAppGetMode(t *testing.T) {
	tests := []struct {
		name       string
		spaceURL   string
		wantResult string
	}{
		{
			name:       "HTTP mode - empty space URL",
			spaceURL:   "",
			wantResult: "HTTP",
		},
		{
			name:       "HTTP mode - regular URL",
			spaceURL:   "http://localhost:8080",
			wantResult: "HTTP",
		},
		{
			name:       "NATS Tunnel mode",
			spaceURL:   "tunneling:username",
			wantResult: "NATS Tunnel",
		},
		{
			name:       "NATS Tunnel mode - long username",
			spaceURL:   "tunneling:longusernamehere",
			wantResult: "NATS Tunnel",
		},
		{
			name:       "HTTP mode - short string",
			spaceURL:   "short",
			wantResult: "HTTP",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Save and restore SPACE_URL
			orig := os.Getenv("SPACE_URL")
			os.Setenv("SPACE_URL", tt.spaceURL)
			defer os.Setenv("SPACE_URL", orig)

			app := &App{}
			result := app.getMode()

			if result != tt.wantResult {
				t.Errorf("getMode() = %q, want %q", result, tt.wantResult)
			}
		})
	}
}

func TestAppGreet(t *testing.T) {
	app := &App{}
	result := app.Greet("World")

	expected := "Hello World! SyftHub Desktop is ready."
	if result != expected {
		t.Errorf("Greet = %q, want %q", result, expected)
	}
}

// Note: Many App methods (GetStatus, HasSettings, GetSettings, GetEndpoints, etc.)
// cannot be tested directly because they call Wails runtime functions that require
// a valid Wails context. These are integration-tested through the Wails framework.

func TestConvertRequestLog(t *testing.T) {
	now := time.Now()

	log := &syfthubapi.RequestLog{
		ID:            "log-123",
		Timestamp:     now,
		CorrelationID: "corr-456",
		EndpointSlug:  "my-endpoint",
		EndpointType:  "model",
		User: &syfthubapi.LogUserInfo{
			ID:       "user-1",
			Username: "testuser",
			Email:    "test@example.com",
			Role:     "admin",
		},
		Request: &syfthubapi.LogRequest{
			Type:    "chat",
			Query:   "hello",
			RawSize: 100,
			Messages: []syfthubapi.Message{
				{Role: "user", Content: "Hello"},
				{Role: "assistant", Content: "Hi there!"},
			},
		},
		Response: &syfthubapi.LogResponse{
			Success:          true,
			Content:          "Response content",
			ContentTruncated: false,
		},
		Policy: &syfthubapi.LogPolicy{
			Evaluated:  true,
			Allowed:    true,
			PolicyName: "rate-limit",
			Reason:     "within limits",
		},
		Timing: &syfthubapi.LogTiming{
			ReceivedAt:  now,
			ProcessedAt: now.Add(100 * time.Millisecond),
			DurationMs:  100,
		},
	}

	entry := convertRequestLog(log)

	if entry.ID != "log-123" {
		t.Errorf("ID = %q, want %q", entry.ID, "log-123")
	}
	if entry.CorrelationID != "corr-456" {
		t.Errorf("CorrelationID = %q, want %q", entry.CorrelationID, "corr-456")
	}
	if entry.EndpointSlug != "my-endpoint" {
		t.Errorf("EndpointSlug = %q, want %q", entry.EndpointSlug, "my-endpoint")
	}

	// Check User
	if entry.User == nil {
		t.Fatal("User should not be nil")
	}
	if entry.User.Username != "testuser" {
		t.Errorf("User.Username = %q, want %q", entry.User.Username, "testuser")
	}

	// Check Request
	if entry.Request == nil {
		t.Fatal("Request should not be nil")
	}
	if entry.Request.Type != "chat" {
		t.Errorf("Request.Type = %q, want %q", entry.Request.Type, "chat")
	}
	if len(entry.Request.Messages) != 2 {
		t.Errorf("len(Request.Messages) = %d, want 2", len(entry.Request.Messages))
	}

	// Check Response
	if entry.Response == nil {
		t.Fatal("Response should not be nil")
	}
	if !entry.Response.Success {
		t.Error("Response.Success should be true")
	}

	// Check Policy
	if entry.Policy == nil {
		t.Fatal("Policy should not be nil")
	}
	if !entry.Policy.Evaluated {
		t.Error("Policy.Evaluated should be true")
	}
	if entry.Policy.PolicyName != "rate-limit" {
		t.Errorf("Policy.PolicyName = %q, want %q", entry.Policy.PolicyName, "rate-limit")
	}

	// Check Timing
	if entry.Timing == nil {
		t.Fatal("Timing should not be nil")
	}
	if entry.Timing.DurationMs != 100 {
		t.Errorf("Timing.DurationMs = %d, want 100", entry.Timing.DurationMs)
	}
}

func TestConvertRequestLogNilFields(t *testing.T) {
	now := time.Now()

	log := &syfthubapi.RequestLog{
		ID:           "log-123",
		Timestamp:    now,
		EndpointSlug: "test",
		// All optional fields are nil
	}

	entry := convertRequestLog(log)

	if entry.User != nil {
		t.Error("User should be nil")
	}
	if entry.Request != nil {
		t.Error("Request should be nil")
	}
	if entry.Response != nil {
		t.Error("Response should be nil")
	}
	if entry.Policy != nil {
		t.Error("Policy should be nil")
	}
	if entry.Timing != nil {
		t.Error("Timing should be nil")
	}
}

func TestConvertRequestLogEmptyMessages(t *testing.T) {
	now := time.Now()

	log := &syfthubapi.RequestLog{
		ID:           "log-123",
		Timestamp:    now,
		EndpointSlug: "test",
		Request: &syfthubapi.LogRequest{
			Type:     "chat",
			Messages: nil, // Empty messages
		},
	}

	entry := convertRequestLog(log)

	if entry.Request == nil {
		t.Fatal("Request should not be nil")
	}
	if entry.Request.Messages != nil {
		t.Errorf("Messages should be nil, got %v", entry.Request.Messages)
	}
}

func TestConvertLogQueryResult(t *testing.T) {
	now := time.Now()

	result := &syfthubapi.LogQueryResult{
		Logs: []*syfthubapi.RequestLog{
			{ID: "log-1", Timestamp: now, EndpointSlug: "ep-1"},
			{ID: "log-2", Timestamp: now, EndpointSlug: "ep-1"},
		},
		Total:   100,
		HasMore: true,
	}

	converted := convertLogQueryResult(result)

	if converted.Total != 100 {
		t.Errorf("Total = %d, want 100", converted.Total)
	}
	if !converted.HasMore {
		t.Error("HasMore should be true")
	}
	if len(converted.Logs) != 2 {
		t.Errorf("len(Logs) = %d, want 2", len(converted.Logs))
	}
}

func TestConvertLogQueryResultEmpty(t *testing.T) {
	result := &syfthubapi.LogQueryResult{
		Logs:    []*syfthubapi.RequestLog{},
		Total:   0,
		HasMore: false,
	}

	converted := convertLogQueryResult(result)

	if converted.Total != 0 {
		t.Errorf("Total = %d, want 0", converted.Total)
	}
	if len(converted.Logs) != 0 {
		t.Errorf("len(Logs) = %d, want 0", len(converted.Logs))
	}
}

func TestConvertLogStats(t *testing.T) {
	now := time.Now()

	stats := &syfthubapi.LogStats{
		TotalRequests:   1000,
		SuccessCount:    950,
		ErrorCount:      40,
		PolicyDenyCount: 10,
		AvgDurationMs:   125.5,
		LastRequestTime: &now,
	}

	converted := convertLogStats(stats)

	if converted.TotalRequests != 1000 {
		t.Errorf("TotalRequests = %d, want 1000", converted.TotalRequests)
	}
	if converted.SuccessCount != 950 {
		t.Errorf("SuccessCount = %d, want 950", converted.SuccessCount)
	}
	if converted.ErrorCount != 40 {
		t.Errorf("ErrorCount = %d, want 40", converted.ErrorCount)
	}
	if converted.PolicyDenyCount != 10 {
		t.Errorf("PolicyDenyCount = %d, want 10", converted.PolicyDenyCount)
	}
	if converted.AvgDurationMs != 125.5 {
		t.Errorf("AvgDurationMs = %f, want 125.5", converted.AvgDurationMs)
	}
	if converted.LastRequestTime == nil {
		t.Error("LastRequestTime should not be nil")
	}
}

func TestConvertLogStatsNilTime(t *testing.T) {
	stats := &syfthubapi.LogStats{
		TotalRequests:   0,
		LastRequestTime: nil,
	}

	converted := convertLogStats(stats)

	if converted.LastRequestTime != nil {
		t.Error("LastRequestTime should be nil")
	}
}

func TestConvertLogStatsZeroValues(t *testing.T) {
	stats := &syfthubapi.LogStats{}

	converted := convertLogStats(stats)

	if converted.TotalRequests != 0 {
		t.Errorf("TotalRequests = %d, want 0", converted.TotalRequests)
	}
	if converted.SuccessCount != 0 {
		t.Errorf("SuccessCount = %d, want 0", converted.SuccessCount)
	}
	if converted.AvgDurationMs != 0 {
		t.Errorf("AvgDurationMs = %f, want 0", converted.AvgDurationMs)
	}
}
