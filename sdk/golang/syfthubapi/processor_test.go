package syfthubapi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// x402PolicyConfig returns the minimal policy declaration that marks an
// endpoint as taking x402 payments. The processor's Process gates PreVerify /
// SettleAfterHandler / runPostSettlementPolicy on Endpoint.HasPaymentPolicy(),
// so tests that exercise those paths MUST set this on their endpoints.
func x402PolicyConfig() []nodeops.Policy {
	return []nodeops.Policy{{
		Name: "pay",
		Type: PolicyTypeX402PayPerRequest,
		Config: map[string]any{
			"currency":  pathUSDContractForTest,
			"amount":    "0.10",
			"recipient": "0x0000000000000000000000000000000000000001",
		},
	}}
}

// pathUSDContractForTest is a fake contract address used only to fill the
// policy config — the processor's payment-policy detection is type-based.
const pathUSDContractForTest = "0x20c0000000000000000000000000000000000000"

func TestNewRequestProcessor(t *testing.T) {
	registry := NewEndpointRegistry()
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	cfg := &ProcessorConfig{
		Registry: registry,
		Logger:   logger,
	}

	proc := NewRequestProcessor(cfg)
	if proc == nil {
		t.Fatal("processor is nil")
	}
}

func TestRequestProcessorSetLogHook(t *testing.T) {
	proc := &RequestProcessor{}

	proc.SetLogHook(func(ctx context.Context, log *RequestLog) {
		// hook set for testing
	})

	if proc.logHook == nil {
		t.Error("logHook should be set")
	}
}

func TestRequestProcessorProcess(t *testing.T) {
	setup := func() (*RequestProcessor, *EndpointRegistry) {
		registry := NewEndpointRegistry()
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		// Mock auth server
		authServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(VerifyTokenResponse{
				Valid:    true,
				Sub:      "user-123",
				Username: "testuser",
				Email:    "test@example.com",
				Role:     "user",
			})
		}))
		t.Cleanup(authServer.Close)

		authClient := NewHubClient(authServer.URL, "test-key", logger)

		proc := NewRequestProcessor(&ProcessorConfig{
			Registry:   registry,
			AuthClient: authClient,
			Logger:     logger,
		})

		return proc, registry
	}

	t.Run("auth fails with no auth client", func(t *testing.T) {
		registry := NewEndpointRegistry()
		var buf bytes.Buffer
		logger := slog.New(slog.NewTextHandler(&buf, nil))

		proc := NewRequestProcessor(&ProcessorConfig{
			Registry:   registry,
			AuthClient: nil,
			Logger:     logger,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "test-ep", Type: "model"},
			SatelliteToken: "valid-token",
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for missing auth client")
		}
		if resp.Error.Code != TunnelErrorCodeAuthFailed {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("endpoint not found", func(t *testing.T) {
		proc, _ := setup()

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "nonexistent", Type: "model"},
			SatelliteToken: "valid-token",
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for nonexistent endpoint")
		}
		if resp.Error.Code != TunnelErrorCodeEndpointNotFound {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("endpoint disabled", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "disabled-ep",
			Name:    "Disabled",
			Type:    EndpointTypeModel,
			Enabled: false,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "disabled-ep", Type: "model"},
			SatelliteToken: "valid-token",
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for disabled endpoint")
		}
		if resp.Error.Code != TunnelErrorCodeEndpointDisabled {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("data source success", func(t *testing.T) {
		proc, registry := setup()

		docsJSON, _ := json.Marshal([]Document{{DocumentID: "doc1", Content: "content1"}})
		registry.Register(&Endpoint{
			Slug:    "ds-ep",
			Name:    "Data Source",
			Type:    EndpointTypeDataSource,
			Enabled: true,
			invoker: &UnifiedInvoker{
				codec:  DataSourceCodec{},
				slug:   "ds-ep",
				epType: EndpointTypeDataSource,
				executor: &mockExecutor{
					executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
						return &ExecutorOutput{Success: true, Result: docsJSON}, nil
					},
				},
			},
		})

		payload, _ := json.Marshal(DataSourceQueryRequest{Messages: "test query"})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "ds-ep", Type: "data_source"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		resp, err := proc.Process(context.Background(), req)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if resp.Status != "success" {
			t.Errorf("status = %q", resp.Status)
		}
		if resp.Timing == nil {
			t.Error("Timing should not be nil")
		}
	})

	t.Run("model success", func(t *testing.T) {
		proc, registry := setup()

		respJSON, _ := json.Marshal("Hello!")
		registry.Register(&Endpoint{
			Slug:    "model-ep",
			Name:    "Model",
			Type:    EndpointTypeModel,
			Enabled: true,
			invoker: &UnifiedInvoker{
				codec:  ModelCodec{},
				slug:   "model-ep",
				epType: EndpointTypeModel,
				executor: &mockExecutor{
					executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
						return &ExecutorOutput{Success: true, Result: respJSON}, nil
					},
				},
			},
		})

		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hi"}},
		})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "model-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		resp, err := proc.Process(context.Background(), req)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if resp.Status != "success" {
			t.Errorf("status = %q", resp.Status)
		}

		// Verify response structure
		var modelResp ModelQueryResponse
		if err := json.Unmarshal(resp.Payload, &modelResp); err != nil {
			t.Fatalf("unmarshal error: %v", err)
		}
		if modelResp.Summary.Message.Content != "Hello!" {
			t.Errorf("content = %q", modelResp.Summary.Message.Content)
		}
	})

	t.Run("handler execution failure", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "failing-ep",
			Name:    "Failing",
			Type:    EndpointTypeModel,
			Enabled: true,
			invoker: &UnifiedInvoker{
				codec:  ModelCodec{},
				slug:   "failing-ep",
				epType: EndpointTypeModel,
				executor: &mockExecutor{
					executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
						return nil, errors.New("handler crashed")
					},
				},
			},
		})

		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hi"}},
		})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "failing-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for handler failure")
		}
		if resp.Error.Code != TunnelErrorCodeExecutionFailed {
			t.Errorf("error code = %q", resp.Error.Code)
		}
	})

	t.Run("invalid payload", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "model-ep",
			Name:    "Model",
			Type:    EndpointTypeModel,
			Enabled: true,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "model-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        json.RawMessage(`invalid json`),
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for invalid payload")
		}
	})

	t.Run("unknown endpoint type", func(t *testing.T) {
		proc, registry := setup()

		registry.Register(&Endpoint{
			Slug:    "unknown-ep",
			Name:    "Unknown",
			Type:    "unknown_type",
			Enabled: true,
		})

		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "unknown-ep", Type: "unknown_type"},
			SatelliteToken: "valid-token",
			Payload:        json.RawMessage(`{}`),
		}

		resp, _ := proc.Process(context.Background(), req)
		if resp.Status != "error" {
			t.Error("should return error for unknown type")
		}
	})

	t.Run("log hook called", func(t *testing.T) {
		proc, registry := setup()

		hookCalled := false
		var capturedLog *RequestLog
		proc.SetLogHook(func(ctx context.Context, log *RequestLog) {
			hookCalled = true
			capturedLog = log
		})

		respJSON, _ := json.Marshal("response")
		registry.Register(&Endpoint{
			Slug:    "logged-ep",
			Name:    "Logged",
			Type:    EndpointTypeModel,
			Enabled: true,
			invoker: &UnifiedInvoker{
				codec:  ModelCodec{},
				slug:   "logged-ep",
				epType: EndpointTypeModel,
				executor: &mockExecutor{
					executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
						return &ExecutorOutput{Success: true, Result: respJSON}, nil
					},
				},
			},
		})

		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hi"}},
		})
		req := &TunnelRequest{
			CorrelationID:  "test-123",
			Endpoint:       TunnelEndpointInfo{Slug: "logged-ep", Type: "model"},
			SatelliteToken: "valid-token",
			Payload:        payload,
		}

		proc.Process(context.Background(), req)

		if !hookCalled {
			t.Error("log hook should be called")
		}
		if capturedLog == nil {
			t.Fatal("captured log is nil")
		}
		if capturedLog.CorrelationID != "test-123" {
			t.Errorf("CorrelationID = %q", capturedLog.CorrelationID)
		}
	})
}

func TestRequestProcessorErrorResponse(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	proc := &RequestProcessor{logger: logger}

	req := &TunnelRequest{
		CorrelationID: "err-123",
		Endpoint:      TunnelEndpointInfo{Slug: "test-ep"},
	}

	resp := proc.errorResponse(req, TunnelErrorCodeExecutionFailed, "test error")

	if resp.Protocol != "syfthub-tunnel/v1" {
		t.Errorf("Protocol = %q", resp.Protocol)
	}
	if resp.Type != "endpoint_response" {
		t.Errorf("Type = %q", resp.Type)
	}
	if resp.Status != "error" {
		t.Errorf("Status = %q", resp.Status)
	}
	if resp.CorrelationID != "err-123" {
		t.Errorf("CorrelationID = %q", resp.CorrelationID)
	}
	if resp.Error.Code != TunnelErrorCodeExecutionFailed {
		t.Errorf("Error.Code = %q", resp.Error.Code)
	}
	if resp.Error.Message != "test error" {
		t.Errorf("Error.Message = %q", resp.Error.Message)
	}
}

// stubGate is a test-only MppxGate that records calls and pretends to
// settle by writing a synthetic receipt + payment_challenge_id into
// metadata, mirroring what mppxgate.TempoGate does on a successful
// PreVerify + SettleAfterHandler round.
type stubGate struct {
	preVerifyCalls  int
	settleCalls     int
	buildChallenges int
	settleErr       error
	writeReceipt    bool
	writeFailure    bool
	challengeID     string
	settleAfterFn   func(metadata map[string]any)
}

func (g *stubGate) PreVerify(ctx context.Context, credential string, metadata map[string]any) error {
	g.preVerifyCalls++
	if g.challengeID != "" {
		metadata["payment_challenge_id"] = g.challengeID
		metadata["payment_nonce"] = uint64(7)
		metadata["payment_verified"] = true
	}
	return nil
}

func (g *stubGate) BuildChallenge(ctx context.Context, spec map[string]any, resultMeta map[string]any) error {
	g.buildChallenges++
	return nil
}

func (g *stubGate) SettleAfterHandler(ctx context.Context, metadata map[string]any) error {
	g.settleCalls++
	if g.settleAfterFn != nil {
		g.settleAfterFn(metadata)
	}
	if g.writeReceipt {
		metadata["payment_receipt"] = map[string]any{
			"reference": "0xdeadbeef",
			"status":    "settled",
		}
		metadata["payment_status"] = "settled"
	}
	if g.writeFailure {
		metadata["payment_failure"] = map[string]any{"reason": "reverted on chain"}
		metadata["payment_status"] = "failed"
	}
	return g.settleErr
}

func setupProcessorWithAuth(t *testing.T) (*RequestProcessor, *EndpointRegistry) {
	t.Helper()
	registry := NewEndpointRegistry()
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	authServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(VerifyTokenResponse{
			Valid:    true,
			Sub:      "user-123",
			Username: "testuser",
			Email:    "test@example.com",
			Role:     "user",
		})
	}))
	t.Cleanup(authServer.Close)

	authClient := NewHubClient(authServer.URL, "test-key", logger)
	proc := NewRequestProcessor(&ProcessorConfig{
		Registry:   registry,
		AuthClient: authClient,
		Logger:     logger,
	})
	return proc, registry
}

func TestProcessor_X402SettlementInvokesPostExecute(t *testing.T) {
	proc, registry := setupProcessorWithAuth(t)

	gate := &stubGate{writeReceipt: true, challengeID: "chal-abc"}
	proc.SetMppxGate(gate)

	var calls []*ExecutorInput
	respJSON, _ := json.Marshal("ok")
	exec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			// Take a defensive copy of the metadata map at the moment of
			// the call so we can assert per-call snapshots without
			// aliasing the shared reqCtx.Metadata.
			cp := *input
			if input.Context != nil {
				ctxCopy := *input.Context
				if input.Context.Metadata != nil {
					mcopy := make(map[string]any, len(input.Context.Metadata))
					for k, v := range input.Context.Metadata {
						mcopy[k] = v
					}
					ctxCopy.Metadata = mcopy
				}
				cp.Context = &ctxCopy
			}
			calls = append(calls, &cp)
			return &ExecutorOutput{Success: true, Result: respJSON}, nil
		},
	}

	paidEP := &Endpoint{
		Slug:    "paid-ep",
		Name:    "Paid",
		Type:    EndpointTypeModel,
		Enabled: true,
		invoker: &UnifiedInvoker{
			codec:    ModelCodec{},
			slug:     "paid-ep",
			epType:   EndpointTypeModel,
			executor: exec,
		},
	}
	paidEP.SetPolicyConfigs(x402PolicyConfig())
	registry.Register(paidEP)

	payload, _ := json.Marshal(ModelQueryRequest{
		Messages: []Message{{Role: "user", Content: "hi"}},
	})
	req := &TunnelRequest{
		CorrelationID:     "x402-1",
		Endpoint:          TunnelEndpointInfo{Slug: "paid-ep", Type: "model"},
		SatelliteToken:    "valid-token",
		Payload:           payload,
		PaymentCredential: "fake-cred",
	}

	resp, err := proc.Process(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != "success" {
		t.Fatalf("status = %q", resp.Status)
	}

	if gate.preVerifyCalls != 1 {
		t.Errorf("PreVerify called %d times, want 1", gate.preVerifyCalls)
	}
	if gate.settleCalls != 1 {
		t.Errorf("SettleAfterHandler called %d times, want 1", gate.settleCalls)
	}
	if len(calls) != 2 {
		t.Fatalf("Execute called %d times, want 2 (pre+handler+post, then post-only)", len(calls))
	}

	first := calls[0]
	if first.PolicyPhase != "" {
		t.Errorf("first Execute PolicyPhase = %q, want empty", first.PolicyPhase)
	}

	second := calls[1]
	if second.PolicyPhase != PolicyPhasePost {
		t.Errorf("second Execute PolicyPhase = %q, want %q", second.PolicyPhase, PolicyPhasePost)
	}
	if len(second.Output) == 0 {
		t.Error("second Execute Output should be non-empty (formatted handler result)")
	}
	if second.Context == nil || second.Context.Metadata == nil {
		t.Fatalf("second Execute Context.Metadata is nil")
	}
	if _, ok := second.Context.Metadata["payment_receipt"]; !ok {
		t.Error("second Execute metadata missing payment_receipt")
	}
	if cid, _ := second.Context.Metadata["payment_challenge_id"].(string); cid != "chal-abc" {
		t.Errorf("second Execute metadata payment_challenge_id = %q, want chal-abc", cid)
	}
	if status, _ := second.Context.Metadata["payment_status"].(string); status != "settled" {
		t.Errorf("second Execute metadata payment_status = %q, want settled", status)
	}
}

func TestProcessor_NoX402_DoesNotDoubleInvoke(t *testing.T) {
	proc, registry := setupProcessorWithAuth(t)

	gate := &stubGate{} // no receipt, no failure — gate present but unused
	proc.SetMppxGate(gate)

	var execCalls int
	respJSON, _ := json.Marshal("ok")
	exec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			execCalls++
			return &ExecutorOutput{Success: true, Result: respJSON}, nil
		},
	}

	registry.Register(&Endpoint{
		Slug:    "free-ep",
		Name:    "Free",
		Type:    EndpointTypeModel,
		Enabled: true,
		invoker: &UnifiedInvoker{
			codec:    ModelCodec{},
			slug:     "free-ep",
			epType:   EndpointTypeModel,
			executor: exec,
		},
	})

	payload, _ := json.Marshal(ModelQueryRequest{
		Messages: []Message{{Role: "user", Content: "hi"}},
	})
	req := &TunnelRequest{
		CorrelationID:  "free-1",
		Endpoint:       TunnelEndpointInfo{Slug: "free-ep", Type: "model"},
		SatelliteToken: "valid-token",
		Payload:        payload,
		// No PaymentCredential
	}

	resp, err := proc.Process(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Status != "success" {
		t.Fatalf("status = %q", resp.Status)
	}
	if gate.preVerifyCalls != 0 {
		t.Errorf("PreVerify should not be called when no credential, got %d", gate.preVerifyCalls)
	}
	// SettleAfterHandler must not run either: the endpoint declares no x402
	// policy, so Process gates it out entirely. Previously the gate was
	// called every time and relied on metadata-cleanliness for safety; the
	// processor now refuses to mutate metadata or broadcast for endpoints
	// the policy chain never required payment for.
	if gate.settleCalls != 0 {
		t.Errorf("SettleAfterHandler calls = %d, want 0 for endpoint with no x402 policy", gate.settleCalls)
	}
	if execCalls != 1 {
		t.Errorf("Execute called %d times, want 1 (no post-settlement re-invoke)", execCalls)
	}
}

func TestProcessor_HandlerFailure_NoSettlement_NoPostInvoke(t *testing.T) {
	proc, registry := setupProcessorWithAuth(t)

	gate := &stubGate{writeReceipt: true, challengeID: "chal-xyz"}
	proc.SetMppxGate(gate)

	var execCalls int
	exec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			execCalls++
			return nil, errors.New("handler crashed")
		},
	}

	registry.Register(&Endpoint{
		Slug:    "broken-ep",
		Name:    "Broken",
		Type:    EndpointTypeModel,
		Enabled: true,
		invoker: &UnifiedInvoker{
			codec:    ModelCodec{},
			slug:     "broken-ep",
			epType:   EndpointTypeModel,
			executor: exec,
		},
	})

	payload, _ := json.Marshal(ModelQueryRequest{
		Messages: []Message{{Role: "user", Content: "hi"}},
	})
	req := &TunnelRequest{
		CorrelationID:     "broken-1",
		Endpoint:          TunnelEndpointInfo{Slug: "broken-ep", Type: "model"},
		SatelliteToken:    "valid-token",
		Payload:           payload,
		PaymentCredential: "fake-cred",
	}

	resp, _ := proc.Process(context.Background(), req)
	if resp.Status != "error" {
		t.Fatalf("status = %q, want error", resp.Status)
	}
	if gate.settleCalls != 0 {
		t.Errorf("SettleAfterHandler should not be called when handler fails, got %d", gate.settleCalls)
	}
	if execCalls != 1 {
		t.Errorf("Execute called %d times, want 1 (handler attempt only; no post-settlement re-invoke)", execCalls)
	}
}

func TestProcessor_X402SettlementReverted_StillInvokesPostExecute(t *testing.T) {
	proc, registry := setupProcessorWithAuth(t)

	// Simulate a broadcast that reverted: SettleAfterHandler writes
	// payment_failure (not payment_receipt). The post-policy round-trip
	// must still run so the Python policy can write status='failed'.
	gate := &stubGate{writeFailure: true, challengeID: "chal-rev"}
	proc.SetMppxGate(gate)

	var calls []*ExecutorInput
	respJSON, _ := json.Marshal("ok")
	exec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			cp := *input
			calls = append(calls, &cp)
			return &ExecutorOutput{Success: true, Result: respJSON}, nil
		},
	}

	revEP := &Endpoint{
		Slug:    "rev-ep",
		Name:    "Reverted",
		Type:    EndpointTypeModel,
		Enabled: true,
		invoker: &UnifiedInvoker{
			codec:    ModelCodec{},
			slug:     "rev-ep",
			epType:   EndpointTypeModel,
			executor: exec,
		},
	}
	revEP.SetPolicyConfigs(x402PolicyConfig())
	registry.Register(revEP)

	payload, _ := json.Marshal(ModelQueryRequest{
		Messages: []Message{{Role: "user", Content: "hi"}},
	})
	req := &TunnelRequest{
		CorrelationID:     "rev-1",
		Endpoint:          TunnelEndpointInfo{Slug: "rev-ep", Type: "model"},
		SatelliteToken:    "valid-token",
		Payload:           payload,
		PaymentCredential: "fake-cred",
	}

	if _, err := proc.Process(context.Background(), req); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(calls) != 2 {
		t.Fatalf("Execute called %d times, want 2", len(calls))
	}
	if calls[1].PolicyPhase != PolicyPhasePost {
		t.Errorf("second Execute PolicyPhase = %q, want %q", calls[1].PolicyPhase, PolicyPhasePost)
	}
}

func TestEnrichLogFallback(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))
	proc := &RequestProcessor{logger: logger}

	t.Run("model request", func(t *testing.T) {
		log := &RequestLog{Request: &LogRequest{}}
		payload, _ := json.Marshal(ModelQueryRequest{
			Messages: []Message{{Role: "user", Content: "Hello"}},
		})
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "model"},
			Payload:  payload,
		}

		proc.enrichLogFallback(log, req)

		if len(log.Request.Messages) != 1 {
			t.Errorf("Messages length = %d", len(log.Request.Messages))
		}
	})

	t.Run("data source request", func(t *testing.T) {
		log := &RequestLog{Request: &LogRequest{}}
		payload, _ := json.Marshal(DataSourceQueryRequest{Messages: "test query"})
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "data_source"},
			Payload:  payload,
		}

		proc.enrichLogFallback(log, req)

		if log.Request.Query != "test query" {
			t.Errorf("Query = %q", log.Request.Query)
		}
	})

	t.Run("nil request in log", func(t *testing.T) {
		log := &RequestLog{}
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "model"},
			Payload:  json.RawMessage(`{}`),
		}

		// Should not panic
		proc.enrichLogFallback(log, req)
	})

	t.Run("invalid json payload", func(t *testing.T) {
		log := &RequestLog{Request: &LogRequest{}}
		req := &TunnelRequest{
			Endpoint: TunnelEndpointInfo{Type: "model"},
			Payload:  json.RawMessage(`invalid`),
		}

		// Should not panic, just not populate messages
		proc.enrichLogFallback(log, req)
		if log.Request.Messages != nil {
			t.Error("Messages should be nil for invalid JSON")
		}
	})
}
