package syfthubapi

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestNewRequestLogID(t *testing.T) {
	id1 := NewRequestLogID()
	id2 := NewRequestLogID()

	if id1 == "" {
		t.Error("ID should not be empty")
	}
	if id1 == id2 {
		t.Error("IDs should be unique")
	}
	// UUID format: 8-4-4-4-12
	if len(id1) != 36 {
		t.Errorf("ID length = %d, want 36", len(id1))
	}
}

func TestTruncateForLog(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		wantLen   int
		wantTrunc bool
	}{
		{
			name:      "short string",
			input:     "hello world",
			wantLen:   11,
			wantTrunc: false,
		},
		{
			name:      "exactly max length",
			input:     strings.Repeat("a", MaxLogContentSize),
			wantLen:   MaxLogContentSize,
			wantTrunc: false,
		},
		{
			name:      "over max length",
			input:     strings.Repeat("a", MaxLogContentSize+100),
			wantLen:   MaxLogContentSize,
			wantTrunc: true,
		},
		{
			name:      "empty string",
			input:     "",
			wantLen:   0,
			wantTrunc: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, truncated := TruncateForLog(tt.input)
			if len(result) != tt.wantLen {
				t.Errorf("length = %d, want %d", len(result), tt.wantLen)
			}
			if truncated != tt.wantTrunc {
				t.Errorf("truncated = %v, want %v", truncated, tt.wantTrunc)
			}
		})
	}
}

func TestMaxLogContentSize(t *testing.T) {
	// Verify constant is 10KB
	if MaxLogContentSize != 10*1024 {
		t.Errorf("MaxLogContentSize = %d, want %d", MaxLogContentSize, 10*1024)
	}
}

func TestBuildRequestLog(t *testing.T) {
	t.Run("success response", func(t *testing.T) {
		startTime := time.Now()
		req := &TunnelRequest{
			CorrelationID: "corr-123",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
			Payload:       json.RawMessage(`{"messages": [{"role": "user", "content": "hi"}]}`),
		}
		userCtx := &UserContext{
			Sub:      "user-123",
			Username: "testuser",
			Email:    "test@example.com",
			Role:     "admin",
		}
		resp := &TunnelResponse{
			Status:  "success",
			Payload: json.RawMessage(`{"summary": {"message": {"content": "Hello!"}}}`),
		}

		log := BuildRequestLog(req, userCtx, resp, nil, startTime)

		if log.ID == "" {
			t.Error("ID should not be empty")
		}
		if log.CorrelationID != "corr-123" {
			t.Errorf("CorrelationID = %q", log.CorrelationID)
		}
		if log.EndpointSlug != "test-ep" {
			t.Errorf("EndpointSlug = %q", log.EndpointSlug)
		}
		if log.EndpointType != "model" {
			t.Errorf("EndpointType = %q", log.EndpointType)
		}

		// User info
		if log.User == nil {
			t.Fatal("User should not be nil")
		}
		if log.User.ID != "user-123" {
			t.Errorf("User.ID = %q", log.User.ID)
		}
		if log.User.Username != "testuser" {
			t.Errorf("User.Username = %q", log.User.Username)
		}

		// Request info
		if log.Request == nil {
			t.Fatal("Request should not be nil")
		}
		if log.Request.Type != "model" {
			t.Errorf("Request.Type = %q", log.Request.Type)
		}

		// Response info
		if log.Response == nil {
			t.Fatal("Response should not be nil")
		}
		if !log.Response.Success {
			t.Error("Response.Success should be true")
		}
		if log.Response.Content == "" {
			t.Error("Response.Content should not be empty")
		}

		// Timing
		if log.Timing == nil {
			t.Fatal("Timing should not be nil")
		}
		if log.Timing.DurationMs < 0 {
			t.Errorf("DurationMs = %d", log.Timing.DurationMs)
		}

		// Policy should be nil when not provided
		if log.Policy != nil {
			t.Error("Policy should be nil when not provided")
		}
	})

	t.Run("error response", func(t *testing.T) {
		req := &TunnelRequest{
			CorrelationID: "corr-456",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "data_source"},
		}
		resp := &TunnelResponse{
			Status: "error",
			Error: &TunnelError{
				Code:    TunnelErrorCodeExecutionFailed,
				Message: "handler crashed",
			},
		}

		log := BuildRequestLog(req, nil, resp, nil, time.Now())

		if log.Response.Success {
			t.Error("Response.Success should be false")
		}
		if log.Response.Error != "handler crashed" {
			t.Errorf("Response.Error = %q", log.Response.Error)
		}
		if log.Response.ErrorCode != "EXECUTION_FAILED" {
			t.Errorf("Response.ErrorCode = %q", log.Response.ErrorCode)
		}
	})

	t.Run("with policy result", func(t *testing.T) {
		req := &TunnelRequest{
			CorrelationID: "corr-789",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
		}
		resp := &TunnelResponse{Status: "success"}
		policyResult := &PolicyResultOutput{
			Allowed:    true,
			PolicyName: "rate_limit",
			Reason:     "within limits",
			Pending:    false,
			Metadata:   map[string]any{"remaining": 99},
		}

		log := BuildRequestLog(req, nil, resp, policyResult, time.Now())

		if log.Policy == nil {
			t.Fatal("Policy should not be nil")
		}
		if !log.Policy.Evaluated {
			t.Error("Policy.Evaluated should be true")
		}
		if !log.Policy.Allowed {
			t.Error("Policy.Allowed should be true")
		}
		if log.Policy.PolicyName != "rate_limit" {
			t.Errorf("Policy.PolicyName = %q", log.Policy.PolicyName)
		}
		if log.Policy.Reason != "within limits" {
			t.Errorf("Policy.Reason = %q", log.Policy.Reason)
		}
	})

	t.Run("nil user context", func(t *testing.T) {
		req := &TunnelRequest{
			CorrelationID: "corr-nil",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
		}
		resp := &TunnelResponse{Status: "success"}

		log := BuildRequestLog(req, nil, resp, nil, time.Now())

		if log.User != nil {
			t.Error("User should be nil")
		}
	})

	t.Run("nil response", func(t *testing.T) {
		req := &TunnelRequest{
			CorrelationID: "corr-nil-resp",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
		}

		log := BuildRequestLog(req, nil, nil, nil, time.Now())

		if log.Response == nil {
			t.Fatal("Response should not be nil even with nil input")
		}
		if log.Response.Success {
			t.Error("Response.Success should be false for nil response")
		}
	})

	t.Run("truncates large response", func(t *testing.T) {
		req := &TunnelRequest{
			CorrelationID: "corr-large",
			Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
		}
		largePayload := strings.Repeat("x", MaxLogContentSize+1000)
		resp := &TunnelResponse{
			Status:  "success",
			Payload: json.RawMessage(largePayload),
		}

		log := BuildRequestLog(req, nil, resp, nil, time.Now())

		if len(log.Response.Content) != MaxLogContentSize {
			t.Errorf("Content length = %d, want %d", len(log.Response.Content), MaxLogContentSize)
		}
		if !log.Response.ContentTruncated {
			t.Error("ContentTruncated should be true")
		}
	})
}

func TestBuildRequestLog_Payment_Required(t *testing.T) {
	req := &TunnelRequest{
		CorrelationID: "corr-pay-req",
		Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
	}
	resp := &TunnelResponse{Status: "success"}
	policyResult := &PolicyResultOutput{
		Allowed: false,
		Pending: true,
		Metadata: map[string]any{
			"challenge_id":      "abc",
			"payment_amount":    "0.10",
			"payment_currency":  "PathUSD",
			"payment_recipient": "0xrecipient",
		},
	}

	log := BuildRequestLog(req, nil, resp, policyResult, time.Now())

	if log.Payment == nil {
		t.Fatal("Payment should not be nil")
	}
	if log.Payment.Status != "required" {
		t.Errorf("Status = %q, want %q", log.Payment.Status, "required")
	}
	if log.Payment.TxHash != "" {
		t.Errorf("TxHash = %q, want empty", log.Payment.TxHash)
	}
	if log.Payment.PaidAt != "" {
		t.Errorf("PaidAt = %q, want empty", log.Payment.PaidAt)
	}
	if log.Payment.ChallengeID != "abc" {
		t.Errorf("ChallengeID = %q", log.Payment.ChallengeID)
	}
	if log.Payment.Amount != "0.10" {
		t.Errorf("Amount = %q", log.Payment.Amount)
	}
	if log.Payment.Currency != "PathUSD" {
		t.Errorf("Currency = %q", log.Payment.Currency)
	}
	if log.Payment.Recipient != "0xrecipient" {
		t.Errorf("Recipient = %q", log.Payment.Recipient)
	}
}

func TestBuildRequestLog_Payment_Verified(t *testing.T) {
	req := &TunnelRequest{
		CorrelationID: "corr-pay-ver",
		Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
	}
	resp := &TunnelResponse{Status: "success"}
	policyResult := &PolicyResultOutput{
		Allowed: true,
		Metadata: map[string]any{
			"challenge_id":      "abc",
			"tx_hash":           "0xdead",
			"payment_amount":    "0.10",
			"payment_currency":  "PathUSD",
			"payment_recipient": "0xrecipient",
		},
	}

	log := BuildRequestLog(req, nil, resp, policyResult, time.Now())

	if log.Payment == nil {
		t.Fatal("Payment should not be nil")
	}
	if log.Payment.Status != "verified" {
		t.Errorf("Status = %q, want %q", log.Payment.Status, "verified")
	}
	if log.Payment.TxHash != "0xdead" {
		t.Errorf("TxHash = %q, want %q", log.Payment.TxHash, "0xdead")
	}
	if log.Payment.PaidAt == "" {
		t.Error("PaidAt should not be empty for verified status")
	}
	// Verify PaidAt parses as RFC3339.
	if _, err := time.Parse(time.RFC3339, log.Payment.PaidAt); err != nil {
		t.Errorf("PaidAt %q is not RFC3339: %v", log.Payment.PaidAt, err)
	}
}

func TestBuildRequestLog_Payment_Failed(t *testing.T) {
	req := &TunnelRequest{
		CorrelationID: "corr-pay-fail",
		Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
	}
	resp := &TunnelResponse{Status: "success"}
	policyResult := &PolicyResultOutput{
		Allowed: false,
		Pending: false,
		Metadata: map[string]any{
			"challenge_id":      "abc",
			"payment_amount":    "0.10",
			"payment_currency":  "PathUSD",
			"payment_recipient": "0xrecipient",
		},
	}

	log := BuildRequestLog(req, nil, resp, policyResult, time.Now())

	if log.Payment == nil {
		t.Fatal("Payment should not be nil")
	}
	if log.Payment.Status != "failed" {
		t.Errorf("Status = %q, want %q", log.Payment.Status, "failed")
	}
	if log.Payment.PaidAt != "" {
		t.Errorf("PaidAt = %q, want empty", log.Payment.PaidAt)
	}
}

func TestBuildRequestLog_NoPolicy_NoPayment(t *testing.T) {
	req := &TunnelRequest{
		CorrelationID: "corr-no-pol",
		Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
	}
	resp := &TunnelResponse{Status: "success"}

	log := BuildRequestLog(req, nil, resp, nil, time.Now())

	if log.Payment != nil {
		t.Errorf("Payment should be nil when policyResult is nil, got %+v", log.Payment)
	}
}

func TestBuildRequestLog_PolicyButNoPaymentMetadata_NoPayment(t *testing.T) {
	req := &TunnelRequest{
		CorrelationID: "corr-no-pay-meta",
		Endpoint:      TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
	}
	resp := &TunnelResponse{Status: "success"}
	policyResult := &PolicyResultOutput{
		Allowed:  true,
		Metadata: map[string]any{"some_other_key": "x"},
	}

	log := BuildRequestLog(req, nil, resp, policyResult, time.Now())

	if log.Payment != nil {
		t.Errorf("Payment should be nil when no payment metadata is present, got %+v", log.Payment)
	}
}

func TestPaymentLog_JSON_Omitempty(t *testing.T) {
	p := &PaymentLog{}
	data, err := json.Marshal(p)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}
	s := string(data)
	if strings.Contains(s, "tx_hash") {
		t.Errorf("empty PaymentLog should omit tx_hash, got: %s", s)
	}
	if strings.Contains(s, "paid_at") {
		t.Errorf("empty PaymentLog should omit paid_at, got: %s", s)
	}
}

func TestRequestLogJSONMarshaling(t *testing.T) {
	log := &RequestLog{
		ID:            "log-123",
		Timestamp:     time.Now(),
		CorrelationID: "corr-123",
		EndpointSlug:  "test-ep",
		EndpointType:  "model",
		User: &LogUserInfo{
			ID:       "user-123",
			Username: "testuser",
		},
		Request: &LogRequest{
			Type:    "model",
			RawSize: 100,
		},
		Response: &LogResponse{
			Success: true,
			Content: "response content",
		},
		Timing: &LogTiming{
			ReceivedAt:  time.Now(),
			ProcessedAt: time.Now(),
			DurationMs:  50,
		},
	}

	data, err := json.Marshal(log)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded RequestLog
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.ID != log.ID {
		t.Errorf("ID = %q, want %q", decoded.ID, log.ID)
	}
	if decoded.CorrelationID != log.CorrelationID {
		t.Errorf("CorrelationID = %q", decoded.CorrelationID)
	}
}

func TestLogUserInfoJSONMarshaling(t *testing.T) {
	user := &LogUserInfo{
		ID:       "user-123",
		Username: "testuser",
		Email:    "test@example.com",
		Role:     "admin",
	}

	data, err := json.Marshal(user)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded LogUserInfo
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded != *user {
		t.Errorf("decoded = %+v, want %+v", decoded, *user)
	}
}

func TestLogRequestJSONMarshaling(t *testing.T) {
	t.Run("model request", func(t *testing.T) {
		req := &LogRequest{
			Type:     "model",
			Messages: []Message{{Role: "user", Content: "Hello"}},
			RawSize:  50,
		}

		data, err := json.Marshal(req)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded LogRequest
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if len(decoded.Messages) != 1 {
			t.Errorf("Messages length = %d", len(decoded.Messages))
		}
	})

	t.Run("data source request", func(t *testing.T) {
		req := &LogRequest{
			Type:    "data_source",
			Query:   "search query",
			RawSize: 20,
		}

		data, err := json.Marshal(req)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded LogRequest
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.Query != "search query" {
			t.Errorf("Query = %q", decoded.Query)
		}
	})
}

func TestLogResponseJSONMarshaling(t *testing.T) {
	resp := &LogResponse{
		Success:          true,
		Content:          "response content",
		ContentTruncated: true,
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded LogResponse
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Success != resp.Success {
		t.Errorf("Success = %v", decoded.Success)
	}
	if decoded.ContentTruncated != resp.ContentTruncated {
		t.Errorf("ContentTruncated = %v", decoded.ContentTruncated)
	}
}

func TestLogPolicyJSONMarshaling(t *testing.T) {
	policy := &LogPolicy{
		Evaluated:  true,
		Allowed:    false,
		PolicyName: "rate_limit",
		Reason:     "exceeded limit",
		Pending:    true,
		Metadata:   map[string]any{"limit": 100, "current": 150},
	}

	data, err := json.Marshal(policy)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded LogPolicy
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Evaluated != policy.Evaluated {
		t.Errorf("Evaluated = %v", decoded.Evaluated)
	}
	if decoded.Allowed != policy.Allowed {
		t.Errorf("Allowed = %v", decoded.Allowed)
	}
	if decoded.PolicyName != policy.PolicyName {
		t.Errorf("PolicyName = %q", decoded.PolicyName)
	}
}

func TestPaymentLogJSONMarshaling(t *testing.T) {
	t.Run("verified payment round-trips", func(t *testing.T) {
		payment := &PaymentLog{
			ChallengeID: "abc",
			TxHash:      "0x1234",
			Amount:      "0.10",
			Currency:    "0xCAFE",
			Recipient:   "0xBEEF",
			Status:      "verified",
			PaidAt:      "2026-05-09T12:00:00Z",
		}

		data, err := json.Marshal(payment)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded PaymentLog
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded != *payment {
			t.Errorf("decoded = %+v, want %+v", decoded, *payment)
		}
	})

	t.Run("required-only payment omits tx_hash and paid_at", func(t *testing.T) {
		payment := &PaymentLog{
			ChallengeID: "abc",
			Amount:      "0.10",
			Currency:    "0xCAFE",
			Recipient:   "0xBEEF",
			Status:      "required",
		}

		data, err := json.Marshal(payment)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		raw := map[string]any{}
		if err := json.Unmarshal(data, &raw); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}
		if _, ok := raw["tx_hash"]; ok {
			t.Error("tx_hash should be omitted when empty")
		}
		if _, ok := raw["paid_at"]; ok {
			t.Error("paid_at should be omitted when empty")
		}
	})
}

func TestRequestLogPaymentField(t *testing.T) {
	t.Run("payment present", func(t *testing.T) {
		log := &RequestLog{
			ID:            "log-1",
			CorrelationID: "corr-1",
			EndpointSlug:  "ep",
			EndpointType:  "model",
			Request:       &LogRequest{Type: "model"},
			Response:      &LogResponse{Success: true},
			Timing:        &LogTiming{},
			Payment: &PaymentLog{
				ChallengeID: "abc",
				Amount:      "0.10",
				Currency:    "0xCAFE",
				Recipient:   "0xBEEF",
				Status:      "verified",
				TxHash:      "0xdead",
				PaidAt:      "2026-05-09T12:00:00Z",
			},
		}

		data, err := json.Marshal(log)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded RequestLog
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}
		if decoded.Payment == nil {
			t.Fatal("Payment should not be nil after round-trip")
		}
		if decoded.Payment.ChallengeID != "abc" {
			t.Errorf("ChallengeID = %q", decoded.Payment.ChallengeID)
		}
		if decoded.Payment.Status != "verified" {
			t.Errorf("Status = %q", decoded.Payment.Status)
		}
	})

	t.Run("payment omitted when nil", func(t *testing.T) {
		log := &RequestLog{
			ID:       "log-2",
			Request:  &LogRequest{Type: "model"},
			Response: &LogResponse{Success: true},
			Timing:   &LogTiming{},
		}
		data, err := json.Marshal(log)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}
		raw := map[string]any{}
		if err := json.Unmarshal(data, &raw); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}
		if _, ok := raw["payment"]; ok {
			t.Error("payment should be omitted when nil")
		}
	})
}

func TestLogTimingJSONMarshaling(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	timing := &LogTiming{
		ReceivedAt:  now,
		ProcessedAt: now.Add(50 * time.Millisecond),
		DurationMs:  50,
	}

	data, err := json.Marshal(timing)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded LogTiming
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.DurationMs != timing.DurationMs {
		t.Errorf("DurationMs = %d", decoded.DurationMs)
	}
}

func TestLogQueryOptionsJSONMarshaling(t *testing.T) {
	now := time.Now()
	opts := &LogQueryOptions{
		Offset:     10,
		Limit:      50,
		StartTime:  &now,
		Status:     "success",
		UserID:     "user-123",
		PolicyOnly: true,
	}

	data, err := json.Marshal(opts)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded LogQueryOptions
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Offset != opts.Offset {
		t.Errorf("Offset = %d", decoded.Offset)
	}
	if decoded.Limit != opts.Limit {
		t.Errorf("Limit = %d", decoded.Limit)
	}
	if decoded.PolicyOnly != opts.PolicyOnly {
		t.Errorf("PolicyOnly = %v", decoded.PolicyOnly)
	}
}

func TestLogQueryResultJSONMarshaling(t *testing.T) {
	result := &LogQueryResult{
		Logs: []*RequestLog{
			{ID: "log-1", CorrelationID: "corr-1"},
			{ID: "log-2", CorrelationID: "corr-2"},
		},
		Total:   100,
		HasMore: true,
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded LogQueryResult
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if len(decoded.Logs) != 2 {
		t.Errorf("Logs length = %d", len(decoded.Logs))
	}
	if decoded.Total != 100 {
		t.Errorf("Total = %d", decoded.Total)
	}
	if !decoded.HasMore {
		t.Error("HasMore should be true")
	}
}

func TestLogStatsJSONMarshaling(t *testing.T) {
	now := time.Now()
	stats := &LogStats{
		TotalRequests:   1000,
		SuccessCount:    950,
		ErrorCount:      40,
		PolicyDenyCount: 10,
		AvgDurationMs:   45.5,
		LastRequestTime: &now,
	}

	data, err := json.Marshal(stats)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded LogStats
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.TotalRequests != stats.TotalRequests {
		t.Errorf("TotalRequests = %d", decoded.TotalRequests)
	}
	if decoded.AvgDurationMs != stats.AvgDurationMs {
		t.Errorf("AvgDurationMs = %f", decoded.AvgDurationMs)
	}
}

// TestBuildRequestLog_StampsStatus verifies that BuildRequestLog stamps the
// Status field based on the response status so downstream consumers (desktop
// log store, frontend) can distinguish completed from failed entries without
// inferring from Response.Success.
func TestBuildRequestLog_StampsStatus(t *testing.T) {
	startTime := time.Now()
	req := &TunnelRequest{
		CorrelationID: "corr-status",
		Endpoint:      TunnelEndpointInfo{Slug: "ep", Type: "model"},
		Payload:       json.RawMessage(`{}`),
	}

	t.Run("success → completed", func(t *testing.T) {
		resp := &TunnelResponse{Status: "success", Payload: json.RawMessage(`{}`)}
		log := BuildRequestLog(req, nil, resp, nil, startTime)
		if log.Status != LogStatusCompleted {
			t.Errorf("Status = %q, want %q", log.Status, LogStatusCompleted)
		}
	})

	t.Run("non-success → failed", func(t *testing.T) {
		resp := &TunnelResponse{
			Status: "error",
			Error:  &TunnelError{Code: TunnelErrorCodeInternalError, Message: "boom"},
		}
		log := BuildRequestLog(req, nil, resp, nil, startTime)
		if log.Status != LogStatusFailed {
			t.Errorf("Status = %q, want %q", log.Status, LogStatusFailed)
		}
	})
}

// TestLogStatusConstants pins the wire values: changing these silently would
// break the in-memory snapshot path in the desktop log store and the frontend
// upsert handler.
func TestLogStatusConstants(t *testing.T) {
	cases := map[string]string{
		LogStatusRunning:    "running",
		LogStatusCompleted:  "completed",
		LogStatusFailed:     "failed",
		LogStatusTerminated: "terminated",
	}
	for got, want := range cases {
		if got != want {
			t.Errorf("status constant = %q, want %q", got, want)
		}
	}
}
