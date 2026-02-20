package syfthubapi

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestEndpointType(t *testing.T) {
	t.Run("constants", func(t *testing.T) {
		if EndpointTypeDataSource != "data_source" {
			t.Errorf("EndpointTypeDataSource = %q, want %q", EndpointTypeDataSource, "data_source")
		}
		if EndpointTypeModel != "model" {
			t.Errorf("EndpointTypeModel = %q, want %q", EndpointTypeModel, "model")
		}
	})

	t.Run("String method", func(t *testing.T) {
		if EndpointTypeDataSource.String() != "data_source" {
			t.Errorf("EndpointTypeDataSource.String() = %q", EndpointTypeDataSource.String())
		}
		if EndpointTypeModel.String() != "model" {
			t.Errorf("EndpointTypeModel.String() = %q", EndpointTypeModel.String())
		}
	})
}

func TestDocument(t *testing.T) {
	t.Run("JSON marshaling", func(t *testing.T) {
		doc := Document{
			DocumentID:      "doc-123",
			Content:         "This is the document content",
			Metadata:        map[string]any{"source": "test", "page": 1},
			SimilarityScore: 0.95,
		}

		data, err := json.Marshal(doc)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded Document
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.DocumentID != doc.DocumentID {
			t.Errorf("DocumentID = %q, want %q", decoded.DocumentID, doc.DocumentID)
		}
		if decoded.Content != doc.Content {
			t.Errorf("Content = %q, want %q", decoded.Content, doc.Content)
		}
		if decoded.SimilarityScore != doc.SimilarityScore {
			t.Errorf("SimilarityScore = %f, want %f", decoded.SimilarityScore, doc.SimilarityScore)
		}
	})

	t.Run("empty metadata omitted", func(t *testing.T) {
		doc := Document{
			DocumentID: "doc-456",
			Content:    "Content",
		}

		data, err := json.Marshal(doc)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		// Metadata should be omitted from JSON
		var raw map[string]any
		if err := json.Unmarshal(data, &raw); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if _, exists := raw["metadata"]; exists {
			t.Error("metadata should be omitted when empty")
		}
	})
}

func TestMessage(t *testing.T) {
	t.Run("JSON round-trip", func(t *testing.T) {
		msg := Message{
			Role:    "user",
			Content: "Hello, how are you?",
		}

		data, err := json.Marshal(msg)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded Message
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.Role != msg.Role || decoded.Content != msg.Content {
			t.Errorf("Message mismatch: got %+v, want %+v", decoded, msg)
		}
	})
}

func TestUserContext(t *testing.T) {
	t.Run("JSON marshaling", func(t *testing.T) {
		ctx := UserContext{
			Sub:      "user-123",
			Email:    "test@example.com",
			Username: "testuser",
			Role:     "admin",
		}

		data, err := json.Marshal(ctx)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded UserContext
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded != ctx {
			t.Errorf("UserContext mismatch: got %+v, want %+v", decoded, ctx)
		}
	})
}

func TestRequestContext(t *testing.T) {
	t.Run("NewRequestContext", func(t *testing.T) {
		rc := NewRequestContext()

		if rc.Metadata == nil {
			t.Error("Metadata should be initialized")
		}
		if rc.StartTime.IsZero() {
			t.Error("StartTime should be set")
		}
	})

	t.Run("SetMetadata", func(t *testing.T) {
		rc := NewRequestContext()
		rc.SetMetadata("key1", "value1")
		rc.SetMetadata("key2", 42)

		if v, ok := rc.GetMetadata("key1"); !ok || v != "value1" {
			t.Errorf("GetMetadata(key1) = %v, %v", v, ok)
		}
		if v, ok := rc.GetMetadata("key2"); !ok || v != 42 {
			t.Errorf("GetMetadata(key2) = %v, %v", v, ok)
		}
	})

	t.Run("GetMetadata with nil map", func(t *testing.T) {
		rc := &RequestContext{}
		v, ok := rc.GetMetadata("key")
		if ok || v != nil {
			t.Error("GetMetadata on nil map should return nil, false")
		}
	})

	t.Run("SetMetadata initializes nil map", func(t *testing.T) {
		rc := &RequestContext{}
		rc.SetMetadata("key", "value")
		if v, ok := rc.GetMetadata("key"); !ok || v != "value" {
			t.Error("SetMetadata should initialize map")
		}
	})
}

func TestDataSourceQueryRequest(t *testing.T) {
	t.Run("JSON unmarshaling", func(t *testing.T) {
		jsonStr := `{
			"messages": "search query text",
			"similarity_threshold": 0.8,
			"limit": 10,
			"include_metadata": true
		}`

		var req DataSourceQueryRequest
		if err := json.Unmarshal([]byte(jsonStr), &req); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if req.Messages != "search query text" {
			t.Errorf("Messages = %q", req.Messages)
		}
		if req.SimilarityThreshold != 0.8 {
			t.Errorf("SimilarityThreshold = %f", req.SimilarityThreshold)
		}
		if req.Limit != 10 {
			t.Errorf("Limit = %d", req.Limit)
		}
		if !req.IncludeMetadata {
			t.Error("IncludeMetadata should be true")
		}
	})

	t.Run("GetQuery", func(t *testing.T) {
		req := DataSourceQueryRequest{Messages: "test query"}
		if req.GetQuery() != "test query" {
			t.Errorf("GetQuery() = %q", req.GetQuery())
		}
	})
}

func TestDataSourceQueryResponse(t *testing.T) {
	t.Run("JSON marshaling", func(t *testing.T) {
		resp := DataSourceQueryResponse{
			References: DataSourceReferences{
				Documents: []Document{
					{DocumentID: "1", Content: "doc1"},
					{DocumentID: "2", Content: "doc2"},
				},
			},
		}

		data, err := json.Marshal(resp)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		// Verify structure matches aggregator expectations
		var raw map[string]any
		if err := json.Unmarshal(data, &raw); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		refs, ok := raw["references"].(map[string]any)
		if !ok {
			t.Fatal("references field missing or wrong type")
		}
		docs, ok := refs["documents"].([]any)
		if !ok {
			t.Fatal("documents field missing or wrong type")
		}
		if len(docs) != 2 {
			t.Errorf("expected 2 documents, got %d", len(docs))
		}
	})
}

func TestModelQueryRequest(t *testing.T) {
	t.Run("JSON unmarshaling", func(t *testing.T) {
		jsonStr := `{
			"messages": [
				{"role": "system", "content": "You are helpful."},
				{"role": "user", "content": "Hello"}
			],
			"max_tokens": 1000,
			"temperature": 0.7,
			"stop_sequences": ["STOP", "END"]
		}`

		var req ModelQueryRequest
		if err := json.Unmarshal([]byte(jsonStr), &req); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if len(req.Messages) != 2 {
			t.Errorf("expected 2 messages, got %d", len(req.Messages))
		}
		if req.MaxTokens != 1000 {
			t.Errorf("MaxTokens = %d", req.MaxTokens)
		}
		if req.Temperature != 0.7 {
			t.Errorf("Temperature = %f", req.Temperature)
		}
		if len(req.StopSequences) != 2 {
			t.Errorf("StopSequences length = %d", len(req.StopSequences))
		}
	})
}

func TestModelQueryResponse(t *testing.T) {
	t.Run("JSON marshaling", func(t *testing.T) {
		resp := ModelQueryResponse{
			Summary: ModelSummary{
				Message: ModelSummaryMessage{
					Content: "This is the response",
				},
				Usage: &ModelUsage{
					PromptTokens:     100,
					CompletionTokens: 50,
					TotalTokens:      150,
				},
			},
		}

		data, err := json.Marshal(resp)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		// Verify structure: summary.message.content
		var raw map[string]any
		if err := json.Unmarshal(data, &raw); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		summary, ok := raw["summary"].(map[string]any)
		if !ok {
			t.Fatal("summary field missing")
		}
		message, ok := summary["message"].(map[string]any)
		if !ok {
			t.Fatal("message field missing")
		}
		content, ok := message["content"].(string)
		if !ok || content != "This is the response" {
			t.Errorf("content = %q", content)
		}
	})

	t.Run("usage omitted when nil", func(t *testing.T) {
		resp := ModelQueryResponse{
			Summary: ModelSummary{
				Message: ModelSummaryMessage{Content: "response"},
			},
		}

		data, err := json.Marshal(resp)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var raw map[string]any
		if err := json.Unmarshal(data, &raw); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		summary := raw["summary"].(map[string]any)
		if _, exists := summary["usage"]; exists {
			t.Error("usage should be omitted when nil")
		}
	})
}

func TestTunnelRequest(t *testing.T) {
	t.Run("JSON unmarshaling", func(t *testing.T) {
		jsonStr := `{
			"protocol": "syfthub-tunnel/v1",
			"type": "endpoint_request",
			"correlation_id": "req-123",
			"reply_to": "reply.subject",
			"endpoint": {"slug": "my-endpoint", "type": "model"},
			"payload": {"messages": [{"role": "user", "content": "hi"}]},
			"timeout_ms": 30000,
			"satellite_token": "token123"
		}`

		var req TunnelRequest
		if err := json.Unmarshal([]byte(jsonStr), &req); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if req.Protocol != "syfthub-tunnel/v1" {
			t.Errorf("Protocol = %q", req.Protocol)
		}
		if req.Type != "endpoint_request" {
			t.Errorf("Type = %q", req.Type)
		}
		if req.CorrelationID != "req-123" {
			t.Errorf("CorrelationID = %q", req.CorrelationID)
		}
		if req.ReplyTo != "reply.subject" {
			t.Errorf("ReplyTo = %q", req.ReplyTo)
		}
		if req.Endpoint.Slug != "my-endpoint" {
			t.Errorf("Endpoint.Slug = %q", req.Endpoint.Slug)
		}
		if req.Endpoint.Type != "model" {
			t.Errorf("Endpoint.Type = %q", req.Endpoint.Type)
		}
		if req.TimeoutMs != 30000 {
			t.Errorf("TimeoutMs = %d", req.TimeoutMs)
		}
		if req.SatelliteToken != "token123" {
			t.Errorf("SatelliteToken = %q", req.SatelliteToken)
		}
	})

	t.Run("helper methods", func(t *testing.T) {
		req := TunnelRequest{
			CorrelationID: "corr-456",
			Endpoint: TunnelEndpointInfo{
				Slug: "test-ep",
				Type: "data_source",
			},
		}

		if req.RequestID() != "corr-456" {
			t.Errorf("RequestID() = %q", req.RequestID())
		}
		if req.EndpointSlug() != "test-ep" {
			t.Errorf("EndpointSlug() = %q", req.EndpointSlug())
		}
		if req.EndpointType() != EndpointTypeDataSource {
			t.Errorf("EndpointType() = %q", req.EndpointType())
		}
	})
}

func TestTunnelResponse(t *testing.T) {
	t.Run("success response", func(t *testing.T) {
		resp := TunnelResponse{
			Protocol:      "syfthub-tunnel/v1",
			Type:          "endpoint_response",
			CorrelationID: "req-123",
			Status:        "success",
			EndpointSlug:  "my-endpoint",
			Payload:       json.RawMessage(`{"result": "data"}`),
			Timing: &TunnelTiming{
				ReceivedAt:  time.Now(),
				ProcessedAt: time.Now(),
				DurationMs:  100,
			},
		}

		data, err := json.Marshal(resp)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded TunnelResponse
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.Status != "success" {
			t.Errorf("Status = %q", decoded.Status)
		}
	})

	t.Run("error response", func(t *testing.T) {
		resp := TunnelResponse{
			Protocol:      "syfthub-tunnel/v1",
			Type:          "endpoint_response",
			CorrelationID: "req-456",
			Status:        "error",
			EndpointSlug:  "my-endpoint",
			Error: &TunnelError{
				Code:    TunnelErrorCodeAuthFailed,
				Message: "Invalid token",
				Details: map[string]any{"reason": "expired"},
			},
		}

		data, err := json.Marshal(resp)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded TunnelResponse
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.Error == nil {
			t.Fatal("Error should not be nil")
		}
		if decoded.Error.Code != TunnelErrorCodeAuthFailed {
			t.Errorf("Error.Code = %q", decoded.Error.Code)
		}
	})
}

func TestTunnelErrorCodes(t *testing.T) {
	codes := []TunnelErrorCode{
		TunnelErrorCodeAuthFailed,
		TunnelErrorCodeEndpointNotFound,
		TunnelErrorCodePolicyDenied,
		TunnelErrorCodeExecutionFailed,
		TunnelErrorCodeTimeout,
		TunnelErrorCodeInvalidRequest,
		TunnelErrorCodeInternalError,
		TunnelErrorCodeEndpointDisabled,
		TunnelErrorCodeRateLimitExceeded,
	}

	expected := []string{
		"AUTH_FAILED",
		"ENDPOINT_NOT_FOUND",
		"POLICY_DENIED",
		"EXECUTION_FAILED",
		"TIMEOUT",
		"INVALID_REQUEST",
		"INTERNAL_ERROR",
		"ENDPOINT_DISABLED",
		"RATE_LIMIT_EXCEEDED",
	}

	for i, code := range codes {
		if string(code) != expected[i] {
			t.Errorf("TunnelErrorCode[%d] = %q, want %q", i, code, expected[i])
		}
	}
}

func TestEndpointInfoJSONMarshal(t *testing.T) {
	t.Run("JSON marshaling with Enabled omitted", func(t *testing.T) {
		info := EndpointInfo{
			Slug:        "test-endpoint",
			Name:        "Test Endpoint",
			Description: "A test endpoint",
			Type:        EndpointTypeModel,
			Enabled:     true, // Should be omitted in JSON
			Version:     "1.0.0",
		}

		data, err := json.Marshal(info)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var raw map[string]any
		if err := json.Unmarshal(data, &raw); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		// Enabled should be omitted (has json:"-" tag)
		if _, exists := raw["enabled"]; exists {
			t.Error("Enabled should be omitted from JSON")
		}
	})

	t.Run("with connect info", func(t *testing.T) {
		info := EndpointInfo{
			Slug: "test",
			Name: "Test",
			Type: EndpointTypeDataSource,
			Connect: []ConnectionInfo{
				{Type: "http", Config: map[string]any{"url": "http://localhost"}},
			},
		}

		data, err := json.Marshal(info)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded EndpointInfo
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if len(decoded.Connect) != 1 {
			t.Errorf("Connect length = %d", len(decoded.Connect))
		}
	})
}

func TestSyncEndpointsRequest(t *testing.T) {
	req := SyncEndpointsRequest{
		Endpoints: []EndpointInfo{
			{Slug: "ep1", Name: "Endpoint 1", Type: EndpointTypeModel},
			{Slug: "ep2", Name: "Endpoint 2", Type: EndpointTypeDataSource},
		},
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded SyncEndpointsRequest
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if len(decoded.Endpoints) != 2 {
		t.Errorf("Endpoints length = %d", len(decoded.Endpoints))
	}
}

func TestVerifyTokenResponse(t *testing.T) {
	t.Run("valid token response", func(t *testing.T) {
		jsonStr := `{
			"valid": true,
			"sub": "user-123",
			"email": "test@example.com",
			"username": "testuser",
			"role": "admin",
			"aud": "syfthub",
			"exp": 1699999999,
			"iat": 1699990000
		}`

		var resp VerifyTokenResponse
		if err := json.Unmarshal([]byte(jsonStr), &resp); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if !resp.Valid {
			t.Error("Valid should be true")
		}
		if resp.Sub != "user-123" {
			t.Errorf("Sub = %q", resp.Sub)
		}

		ctx := resp.ToUserContext()
		if ctx == nil {
			t.Fatal("ToUserContext returned nil")
		}
		if ctx.Sub != "user-123" {
			t.Errorf("UserContext.Sub = %q", ctx.Sub)
		}
		if ctx.Email != "test@example.com" {
			t.Errorf("UserContext.Email = %q", ctx.Email)
		}
	})

	t.Run("invalid token response", func(t *testing.T) {
		jsonStr := `{
			"valid": false,
			"error": "token_expired",
			"message": "Token has expired"
		}`

		var resp VerifyTokenResponse
		if err := json.Unmarshal([]byte(jsonStr), &resp); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if resp.Valid {
			t.Error("Valid should be false")
		}

		ctx := resp.ToUserContext()
		if ctx != nil {
			t.Error("ToUserContext should return nil for invalid token")
		}
	})

	t.Run("valid but empty sub", func(t *testing.T) {
		resp := VerifyTokenResponse{Valid: true, Sub: ""}
		ctx := resp.ToUserContext()
		if ctx != nil {
			t.Error("ToUserContext should return nil when Sub is empty")
		}
	})
}

func TestHeartbeatRequest(t *testing.T) {
	req := HeartbeatRequest{TTLSeconds: 300}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded HeartbeatRequest
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.TTLSeconds != 300 {
		t.Errorf("TTLSeconds = %d", decoded.TTLSeconds)
	}
}

func TestHeartbeatResponse(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	resp := HeartbeatResponse{
		EffectiveTTLSeconds: 300,
		ExpiresAt:           now,
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded HeartbeatResponse
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.EffectiveTTLSeconds != 300 {
		t.Errorf("EffectiveTTLSeconds = %d", decoded.EffectiveTTLSeconds)
	}
}

func TestExecutorInput(t *testing.T) {
	t.Run("data source input", func(t *testing.T) {
		input := ExecutorInput{
			Type:  "data_source",
			Query: "search query",
			Context: &ExecutionContext{
				UserID:       "user-123",
				EndpointSlug: "my-ds",
			},
		}

		data, err := json.Marshal(input)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded ExecutorInput
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.Type != "data_source" {
			t.Errorf("Type = %q", decoded.Type)
		}
		if decoded.Query != "search query" {
			t.Errorf("Query = %q", decoded.Query)
		}
	})

	t.Run("model input", func(t *testing.T) {
		input := ExecutorInput{
			Type: "model",
			Messages: []Message{
				{Role: "user", Content: "Hello"},
			},
			HandlerPath: "/path/to/runner.py",
			WorkDir:     "/path/to/endpoint",
		}

		data, err := json.Marshal(input)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded ExecutorInput
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if len(decoded.Messages) != 1 {
			t.Errorf("Messages length = %d", len(decoded.Messages))
		}
	})

	t.Run("input with transaction token", func(t *testing.T) {
		input := ExecutorInput{
			Type:             "data_source",
			Query:            "search query",
			TransactionToken: "txn_abc123.salt.1234567890.signature",
			Context: &ExecutionContext{
				UserID:       "user-123",
				EndpointSlug: "billing-endpoint",
			},
		}

		data, err := json.Marshal(input)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		// Verify JSON contains transaction_token
		if !strings.Contains(string(data), `"transaction_token"`) {
			t.Errorf("JSON should contain transaction_token field")
		}

		var decoded ExecutorInput
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.TransactionToken != "txn_abc123.salt.1234567890.signature" {
			t.Errorf("TransactionToken = %q", decoded.TransactionToken)
		}
	})

	t.Run("input without transaction token omits field", func(t *testing.T) {
		input := ExecutorInput{
			Type:  "data_source",
			Query: "search query",
		}

		data, err := json.Marshal(input)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		// Verify JSON does not contain transaction_token when empty
		if strings.Contains(string(data), `"transaction_token"`) {
			t.Errorf("JSON should not contain transaction_token field when empty")
		}
	})
}

func TestExecutorOutput(t *testing.T) {
	t.Run("success output", func(t *testing.T) {
		output := ExecutorOutput{
			Success: true,
			Result:  json.RawMessage(`{"documents": []}`),
		}

		data, err := json.Marshal(output)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded ExecutorOutput
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if !decoded.Success {
			t.Error("Success should be true")
		}
	})

	t.Run("error output", func(t *testing.T) {
		output := ExecutorOutput{
			Success:   false,
			Error:     "Import error",
			ErrorType: "ImportError",
		}

		data, err := json.Marshal(output)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded ExecutorOutput
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.Success {
			t.Error("Success should be false")
		}
		if decoded.Error != "Import error" {
			t.Errorf("Error = %q", decoded.Error)
		}
	})

	t.Run("with policy result", func(t *testing.T) {
		output := ExecutorOutput{
			Success: true,
			Result:  json.RawMessage(`{}`),
			PolicyResult: &PolicyResultOutput{
				Allowed: true,
			},
		}

		data, err := json.Marshal(output)
		if err != nil {
			t.Fatalf("Marshal error: %v", err)
		}

		var decoded ExecutorOutput
		if err := json.Unmarshal(data, &decoded); err != nil {
			t.Fatalf("Unmarshal error: %v", err)
		}

		if decoded.PolicyResult == nil {
			t.Fatal("PolicyResult should not be nil")
		}
		if !decoded.PolicyResult.Allowed {
			t.Error("PolicyResult.Allowed should be true")
		}
	})
}

func TestNATSCredentials(t *testing.T) {
	creds := NATSCredentials{
		URL:     "nats://localhost:4222",
		Token:   "secret-token",
		Subject: "space.requests",
	}

	data, err := json.Marshal(creds)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded NATSCredentials
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.URL != creds.URL {
		t.Errorf("URL = %q", decoded.URL)
	}
	if decoded.Token != creds.Token {
		t.Errorf("Token = %q", decoded.Token)
	}
	if decoded.Subject != creds.Subject {
		t.Errorf("Subject = %q", decoded.Subject)
	}
}
