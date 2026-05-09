package syfthubapi

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

func TestValidateSlug(t *testing.T) {
	tests := []struct {
		name    string
		slug    string
		wantErr bool
	}{
		// Valid slugs
		{"simple lowercase", "myendpoint", false},
		{"with hyphens", "my-endpoint", false},
		{"with underscores", "my_endpoint", false},
		{"with numbers", "endpoint123", false},
		{"mixed valid chars", "my-endpoint_v2", false},
		{"single char", "a", false},
		{"max length 64", "a123456789012345678901234567890123456789012345678901234567890123", false},

		// Invalid slugs
		{"empty", "", true},
		{"uppercase", "MyEndpoint", true},
		{"starts with hyphen", "-endpoint", true},
		{"starts with underscore", "_endpoint", true},
		{"contains spaces", "my endpoint", true},
		{"contains dots", "my.endpoint", true},
		{"contains special chars", "my@endpoint", true},
		{"too long 65 chars", "a1234567890123456789012345678901234567890123456789012345678901234", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateSlug(tt.slug)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateSlug(%q) error = %v, wantErr %v", tt.slug, err, tt.wantErr)
			}
			if err != nil && !errors.Is(err, ErrEndpointRegistration) {
				t.Error("error should be EndpointRegistrationError")
			}
		})
	}
}

func TestEndpointInfo(t *testing.T) {
	ep := &Endpoint{
		Slug:        "test-ep",
		Name:        "Test Endpoint",
		Description: "A test endpoint",
		Type:        EndpointTypeModel,
		Enabled:     true,
		Version:     "1.0.0",
		Readme:      "# Test\nThis is a test.",
	}

	info := ep.Info()

	if info.Slug != ep.Slug {
		t.Errorf("Slug = %q, want %q", info.Slug, ep.Slug)
	}
	if info.Name != ep.Name {
		t.Errorf("Name = %q, want %q", info.Name, ep.Name)
	}
	if info.Description != ep.Description {
		t.Errorf("Description = %q, want %q", info.Description, ep.Description)
	}
	if info.Type != ep.Type {
		t.Errorf("Type = %q, want %q", info.Type, ep.Type)
	}
	if info.Enabled != ep.Enabled {
		t.Errorf("Enabled = %v, want %v", info.Enabled, ep.Enabled)
	}
	if info.Version != ep.Version {
		t.Errorf("Version = %q, want %q", info.Version, ep.Version)
	}
	if info.Readme != ep.Readme {
		t.Errorf("Readme = %q, want %q", info.Readme, ep.Readme)
	}
}

func TestEndpoint_Info_PoliciesPopulated(t *testing.T) {
	ep := &Endpoint{
		Slug: "paid-ep",
		Type: EndpointTypeModel,
	}
	ep.SetPolicyConfigs([]nodeops.Policy{
		{
			Name: "rate",
			Type: PolicyTypeRateLimit,
			Config: map[string]interface{}{
				"requests_per_minute": 10,
				"_internal":           "drop me",
				"signing_key":         "drop me too",
			},
		},
		{
			Name: "pay",
			Type: PolicyTypeTransaction,
			Config: map[string]interface{}{
				"recipient":       "0xabc",
				"amount":          "100",
				"currency":        "USDC",
				"method":          "tempo",
				"intent":          "pay-per-call",
				"chain_id":        "tempo-mainnet",
				"ttl_seconds":     60,
				"secret_key_path": "/tmp/secret",
				"signing_key":     "supersecret",
			},
		},
	})

	info := ep.Info()
	if len(info.Policies) != 2 {
		t.Fatalf("expected 2 policies, got %d", len(info.Policies))
	}

	// First policy: rate_limit — passthrough minus underscore/secret keys.
	rate := info.Policies[0]
	if rate["name"] != "rate" || rate["type"] != PolicyTypeRateLimit {
		t.Errorf("unexpected rate header: %+v", rate)
	}
	rateCfg, ok := rate["config"].(map[string]any)
	if !ok {
		t.Fatalf("rate config not map: %T", rate["config"])
	}
	if _, present := rateCfg["_internal"]; present {
		t.Error("underscore key should be stripped")
	}
	if _, present := rateCfg["signing_key"]; present {
		t.Error("signing_key should be stripped from non-transaction policy")
	}
	if rateCfg["requests_per_minute"] != 10 {
		t.Errorf("requests_per_minute should pass through: %+v", rateCfg)
	}

	// Second policy: transaction — strict allow-list, secrets dropped.
	pay := info.Policies[1]
	if pay["name"] != "pay" || pay["type"] != PolicyTypeTransaction {
		t.Errorf("unexpected pay header: %+v", pay)
	}
	payCfg, ok := pay["config"].(map[string]any)
	if !ok {
		t.Fatalf("pay config not map: %T", pay["config"])
	}
	if _, present := payCfg["secret_key_path"]; present {
		t.Error("secret_key_path must not appear in published transaction config")
	}
	if _, present := payCfg["signing_key"]; present {
		t.Error("signing_key must not appear in published transaction config")
	}
	for _, key := range []string{"recipient", "amount", "currency", "method", "intent", "chain_id", "ttl_seconds"} {
		if _, present := payCfg[key]; !present {
			t.Errorf("expected key %q to remain in transaction config: %+v", key, payCfg)
		}
	}
}

func TestEndpoint_Info_PoliciesEmpty(t *testing.T) {
	ep := &Endpoint{Slug: "no-policies", Type: EndpointTypeModel}

	info := ep.Info()
	if info.Policies != nil {
		t.Errorf("Policies should be nil when no configs set, got %#v", info.Policies)
	}

	// Round-trip JSON — `omitempty` should drop the field entirely.
	b, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var generic map[string]any
	if err := json.Unmarshal(b, &generic); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, present := generic["policies"]; present {
		t.Errorf("policies field should be omitted from JSON when empty: %s", string(b))
	}
}

func TestBuildExecutorInput_PaymentCredential(t *testing.T) {
	ep := &Endpoint{Slug: "ep", Type: EndpointTypeModel}
	reqCtx := NewRequestContext()
	reqCtx.User = &UserContext{Username: "alice"}
	reqCtx.PaymentCredential = "Payment eyJ..."

	input := ep.buildExecutorInput("model", reqCtx)
	if input.PaymentCredential != "Payment eyJ..." {
		t.Errorf("PaymentCredential = %q, want %q", input.PaymentCredential, "Payment eyJ...")
	}
}

func TestSanitizePolicyConfig_RemovesSecrets(t *testing.T) {
	t.Run("non-transaction policy strips underscore and secret keys", func(t *testing.T) {
		cfg := map[string]any{
			"_secret_key":     "drop",
			"signing_key":     "drop",
			"secret_key_path": "drop",
			"api_key":         "drop",
			"password":        "drop",
			"auth_token":      "drop",
			"private_key":     "drop",
			"recipient":       "0xabc",
			"amount":          "100",
		}
		got := sanitizePolicyConfig(PolicyTypeRateLimit, cfg)
		want := map[string]any{
			"recipient": "0xabc",
			"amount":    "100",
		}
		if len(got) != len(want) {
			t.Fatalf("expected %d keys, got %d (%+v)", len(want), len(got), got)
		}
		for k, v := range want {
			if got[k] != v {
				t.Errorf("key %q = %v, want %v", k, got[k], v)
			}
		}
	})

	t.Run("transaction policy uses allow-list", func(t *testing.T) {
		cfg := map[string]any{
			"recipient":       "0xabc",
			"amount":          "100",
			"currency":        "USDC",
			"method":          "tempo",
			"intent":          "pay-per-call",
			"chain_id":        "tempo-mainnet",
			"ttl_seconds":     60,
			"secret_key_path": "/tmp/secret",
			"signing_key":     "drop",
			"_anything":       "drop",
			"unknown_field":   "drop",
		}
		got := sanitizePolicyConfig(PolicyTypeTransaction, cfg)
		for _, leak := range []string{"secret_key_path", "signing_key", "_anything", "unknown_field"} {
			if _, present := got[leak]; present {
				t.Errorf("transaction config leaked %q", leak)
			}
		}
		for _, want := range []string{"recipient", "amount", "currency", "method", "intent", "chain_id", "ttl_seconds"} {
			if _, present := got[want]; !present {
				t.Errorf("transaction config missing %q", want)
			}
		}
	})

	t.Run("nil config returns empty map", func(t *testing.T) {
		got := sanitizePolicyConfig(PolicyTypeRateLimit, nil)
		if got == nil || len(got) != 0 {
			t.Errorf("expected empty map, got %#v", got)
		}
	})
}

func TestEndpointSetExecutor(t *testing.T) {
	ep := &Endpoint{Slug: "test"}

	if ep.IsFileBased() {
		t.Error("new endpoint should not be file-based")
	}

	mockExec := &mockExecutor{}
	ep.SetExecutor(mockExec)

	if !ep.IsFileBased() {
		t.Error("endpoint should be file-based after SetExecutor")
	}
}

// mockExecutor implements the Executor interface for testing
type mockExecutor struct {
	executeFunc func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error)
	closed      bool
}

func (m *mockExecutor) Execute(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
	if m.executeFunc != nil {
		return m.executeFunc(ctx, input)
	}
	return &ExecutorOutput{Success: true}, nil
}

func (m *mockExecutor) Close() error {
	m.closed = true
	return nil
}

func TestEndpointInvokeDataSource(t *testing.T) {
	t.Run("wrong type returns error", func(t *testing.T) {
		ep := &Endpoint{
			Slug: "model-ep",
			Type: EndpointTypeModel,
		}

		_, err := ep.InvokeDataSource(context.Background(), "query", nil)
		if err == nil {
			t.Fatal("expected error for wrong type")
		}
		if !errors.Is(err, ErrExecutionFailed) {
			t.Error("error should be ExecutionError")
		}
	})

	t.Run("no handler returns error", func(t *testing.T) {
		ep := &Endpoint{
			Slug: "ds-ep",
			Type: EndpointTypeDataSource,
		}

		_, err := ep.InvokeDataSource(context.Background(), "query", nil)
		if err == nil {
			t.Fatal("expected error for no handler")
		}
		var execErr *ExecutionError
		if !errors.As(err, &execErr) {
			t.Error("error should be ExecutionError")
		}
		if execErr.Message != "no handler registered" {
			t.Errorf("unexpected message: %q", execErr.Message)
		}
	})

	t.Run("calls handler", func(t *testing.T) {
		handlerCalled := false
		ep := &Endpoint{
			Slug: "ds-ep",
			Type: EndpointTypeDataSource,
			dataSourceHandler: func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
				handlerCalled = true
				if query != "test query" {
					t.Errorf("query = %q, want %q", query, "test query")
				}
				return []Document{{DocumentID: "1", Content: "result"}}, nil
			},
		}

		docs, err := ep.InvokeDataSource(context.Background(), "test query", nil)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if !handlerCalled {
			t.Error("handler should have been called")
		}
		if len(docs) != 1 || docs[0].DocumentID != "1" {
			t.Errorf("unexpected result: %+v", docs)
		}
	})

	t.Run("file-based with executor", func(t *testing.T) {
		docsJSON, _ := json.Marshal([]Document{{DocumentID: "doc1", Content: "content"}})
		ep := &Endpoint{
			Slug:        "ds-ep",
			Type:        EndpointTypeDataSource,
			isFileBased: true,
			executor: &mockExecutor{
				executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
					if input.Type != "data_source" {
						t.Errorf("input.Type = %q", input.Type)
					}
					if input.Query != "test query" {
						t.Errorf("input.Query = %q", input.Query)
					}
					return &ExecutorOutput{
						Success: true,
						Result:  json.RawMessage(docsJSON),
					}, nil
				},
			},
		}

		docs, err := ep.InvokeDataSource(context.Background(), "test query", nil)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(docs) != 1 {
			t.Errorf("expected 1 document, got %d", len(docs))
		}
	})

	t.Run("executor returns error", func(t *testing.T) {
		ep := &Endpoint{
			Slug:        "ds-ep",
			Type:        EndpointTypeDataSource,
			isFileBased: true,
			executor: &mockExecutor{
				executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
					return nil, errors.New("subprocess failed")
				},
			},
		}

		_, err := ep.InvokeDataSource(context.Background(), "query", nil)
		if err == nil {
			t.Fatal("expected error")
		}
	})

	t.Run("executor returns failure", func(t *testing.T) {
		ep := &Endpoint{
			Slug:        "ds-ep",
			Type:        EndpointTypeDataSource,
			isFileBased: true,
			executor: &mockExecutor{
				executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
					return &ExecutorOutput{
						Success:   false,
						Error:     "handler crashed",
						ErrorType: "RuntimeError",
					}, nil
				},
			},
		}

		_, err := ep.InvokeDataSource(context.Background(), "query", nil)
		if err == nil {
			t.Fatal("expected error")
		}
		var execErr *ExecutionError
		if !errors.As(err, &execErr) {
			t.Error("should be ExecutionError")
		}
		if execErr.ErrorType != "RuntimeError" {
			t.Errorf("ErrorType = %q", execErr.ErrorType)
		}
	})

	t.Run("with request context", func(t *testing.T) {
		ep := &Endpoint{
			Slug:        "ds-ep",
			Type:        EndpointTypeDataSource,
			isFileBased: true,
			executor: &mockExecutor{
				executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
					if input.Context == nil {
						t.Error("Context should not be nil")
					}
					if input.Context.UserID != "testuser" {
						t.Errorf("UserID = %q", input.Context.UserID)
					}
					docsJSON, _ := json.Marshal([]Document{})
					return &ExecutorOutput{
						Success: true,
						Result:  json.RawMessage(docsJSON),
						PolicyResult: &PolicyResultOutput{
							Allowed: true,
						},
					}, nil
				},
			},
		}

		reqCtx := NewRequestContext()
		reqCtx.User = &UserContext{Username: "testuser"}

		_, err := ep.InvokeDataSource(context.Background(), "query", reqCtx)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if reqCtx.PolicyResult == nil {
			t.Error("PolicyResult should be captured")
		}
	})
}

func TestEndpointInvokeModel(t *testing.T) {
	t.Run("wrong type returns error", func(t *testing.T) {
		ep := &Endpoint{
			Slug: "ds-ep",
			Type: EndpointTypeDataSource,
		}

		_, err := ep.InvokeModel(context.Background(), nil, nil)
		if err == nil {
			t.Fatal("expected error for wrong type")
		}
	})

	t.Run("no handler returns error", func(t *testing.T) {
		ep := &Endpoint{
			Slug: "model-ep",
			Type: EndpointTypeModel,
		}

		_, err := ep.InvokeModel(context.Background(), nil, nil)
		if err == nil {
			t.Fatal("expected error for no handler")
		}
	})

	t.Run("calls handler", func(t *testing.T) {
		ep := &Endpoint{
			Slug: "model-ep",
			Type: EndpointTypeModel,
			modelHandler: func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
				if len(messages) != 1 || messages[0].Content != "Hello" {
					t.Errorf("unexpected messages: %+v", messages)
				}
				return "Hi there!", nil
			},
		}

		result, err := ep.InvokeModel(context.Background(), []Message{{Role: "user", Content: "Hello"}}, nil)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result != "Hi there!" {
			t.Errorf("result = %q", result)
		}
	})

	t.Run("file-based with executor", func(t *testing.T) {
		resultJSON, _ := json.Marshal("Generated response")
		ep := &Endpoint{
			Slug:        "model-ep",
			Type:        EndpointTypeModel,
			isFileBased: true,
			executor: &mockExecutor{
				executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
					if input.Type != "model" {
						t.Errorf("input.Type = %q", input.Type)
					}
					if len(input.Messages) != 1 {
						t.Errorf("expected 1 message, got %d", len(input.Messages))
					}
					return &ExecutorOutput{
						Success: true,
						Result:  json.RawMessage(resultJSON),
					}, nil
				},
			},
		}

		result, err := ep.InvokeModel(context.Background(), []Message{{Role: "user", Content: "Hi"}}, nil)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if result != "Generated response" {
			t.Errorf("result = %q", result)
		}
	})
}

func TestEndpointRegistry(t *testing.T) {
	t.Run("NewEndpointRegistry", func(t *testing.T) {
		reg := NewEndpointRegistry()
		if reg == nil {
			t.Fatal("registry is nil")
		}
		if len(reg.List()) != 0 {
			t.Error("new registry should be empty")
		}
	})

	t.Run("Register and Get", func(t *testing.T) {
		reg := NewEndpointRegistry()
		ep := &Endpoint{Slug: "test-ep", Name: "Test"}

		err := reg.Register(ep)
		if err != nil {
			t.Fatalf("Register error: %v", err)
		}

		got, ok := reg.Get("test-ep")
		if !ok {
			t.Fatal("endpoint not found")
		}
		if got.Name != "Test" {
			t.Errorf("Name = %q", got.Name)
		}
	})

	t.Run("Register duplicate returns error", func(t *testing.T) {
		reg := NewEndpointRegistry()
		ep1 := &Endpoint{Slug: "test-ep", Name: "First"}
		ep2 := &Endpoint{Slug: "test-ep", Name: "Second"}

		err := reg.Register(ep1)
		if err != nil {
			t.Fatalf("first Register error: %v", err)
		}

		err = reg.Register(ep2)
		if err == nil {
			t.Fatal("expected error for duplicate slug")
		}
		if !errors.Is(err, ErrEndpointRegistration) {
			t.Error("error should be EndpointRegistrationError")
		}
	})

	t.Run("Get non-existent returns false", func(t *testing.T) {
		reg := NewEndpointRegistry()
		_, ok := reg.Get("non-existent")
		if ok {
			t.Error("should return false for non-existent endpoint")
		}
	})

	t.Run("List returns all endpoints", func(t *testing.T) {
		reg := NewEndpointRegistry()
		reg.Register(&Endpoint{Slug: "ep1"})
		reg.Register(&Endpoint{Slug: "ep2"})
		reg.Register(&Endpoint{Slug: "ep3"})

		list := reg.List()
		if len(list) != 3 {
			t.Errorf("expected 3 endpoints, got %d", len(list))
		}
	})

	t.Run("Remove existing endpoint", func(t *testing.T) {
		reg := NewEndpointRegistry()
		reg.Register(&Endpoint{Slug: "test-ep"})

		removed := reg.Remove("test-ep")
		if !removed {
			t.Error("Remove should return true for existing endpoint")
		}

		_, ok := reg.Get("test-ep")
		if ok {
			t.Error("endpoint should be removed")
		}
	})

	t.Run("Remove non-existent returns false", func(t *testing.T) {
		reg := NewEndpointRegistry()
		removed := reg.Remove("non-existent")
		if removed {
			t.Error("Remove should return false for non-existent endpoint")
		}
	})

	t.Run("Clear removes all", func(t *testing.T) {
		reg := NewEndpointRegistry()
		reg.Register(&Endpoint{Slug: "ep1"})
		reg.Register(&Endpoint{Slug: "ep2"})

		reg.Clear()

		if len(reg.List()) != 0 {
			t.Error("Clear should remove all endpoints")
		}
	})

	t.Run("ReplaceFileBased", func(t *testing.T) {
		reg := NewEndpointRegistry()

		// Add code-based endpoint
		reg.Register(&Endpoint{Slug: "code-ep", isFileBased: false})

		// Add file-based endpoints
		mockExec := &mockExecutor{}
		reg.Register(&Endpoint{Slug: "file-ep1", isFileBased: true, executor: mockExec})
		reg.Register(&Endpoint{Slug: "file-ep2", isFileBased: true})

		// Replace file-based
		newEndpoints := []*Endpoint{
			{Slug: "new-file-ep1"},
			{Slug: "new-file-ep2"},
		}
		reg.ReplaceFileBased(newEndpoints)

		// Code-based should remain
		_, ok := reg.Get("code-ep")
		if !ok {
			t.Error("code-based endpoint should remain")
		}

		// Old file-based should be removed
		_, ok = reg.Get("file-ep1")
		if ok {
			t.Error("old file-based endpoint should be removed")
		}

		// New file-based should exist
		_, ok = reg.Get("new-file-ep1")
		if !ok {
			t.Error("new file-based endpoint should exist")
		}

		// Executor should be closed
		if !mockExec.closed {
			t.Error("old executor should be closed")
		}
	})

	t.Run("ReplaceFileBased preserves reused executors", func(t *testing.T) {
		reg := NewEndpointRegistry()

		// Simulate selective reload: two endpoints where only one is recreated.
		sharedExec := &mockExecutor{} // executor reused by unchanged endpoint
		staleExec := &mockExecutor{}  // executor replaced during reload

		reg.Register(&Endpoint{Slug: "unchanged-ep", isFileBased: true, executor: sharedExec})
		reg.Register(&Endpoint{Slug: "changed-ep", isFileBased: true, executor: staleExec})

		newExec := &mockExecutor{} // fresh executor for the changed endpoint
		reg.ReplaceFileBased([]*Endpoint{
			{Slug: "unchanged-ep", executor: sharedExec}, // same instance reused
			{Slug: "changed-ep", executor: newExec},      // new instance
		})

		// Reused executor must NOT be closed
		if sharedExec.closed {
			t.Error("reused executor should not be closed")
		}

		// Stale executor must be closed
		if !staleExec.closed {
			t.Error("stale executor should be closed")
		}

		// New executor must not be closed
		if newExec.closed {
			t.Error("new executor should not be closed")
		}

		// Both endpoints should be in registry
		if _, ok := reg.Get("unchanged-ep"); !ok {
			t.Error("unchanged endpoint should be in registry")
		}
		if _, ok := reg.Get("changed-ep"); !ok {
			t.Error("changed endpoint should be in registry")
		}
	})

	t.Run("ReplaceFileBased preserves reused policy executors", func(t *testing.T) {
		reg := NewEndpointRegistry()

		sharedPolicyExec := &mockExecutor{}
		stalePolicyExec := &mockExecutor{}

		reg.Register(&Endpoint{Slug: "agent1", isFileBased: true, policyExecutor: sharedPolicyExec})
		reg.Register(&Endpoint{Slug: "agent2", isFileBased: true, policyExecutor: stalePolicyExec})

		newPolicyExec := &mockExecutor{}
		reg.ReplaceFileBased([]*Endpoint{
			{Slug: "agent1", policyExecutor: sharedPolicyExec},
			{Slug: "agent2", policyExecutor: newPolicyExec},
		})

		if sharedPolicyExec.closed {
			t.Error("reused policy executor should not be closed")
		}
		if !stalePolicyExec.closed {
			t.Error("stale policy executor should be closed")
		}
		if newPolicyExec.closed {
			t.Error("new policy executor should not be closed")
		}
	})

	t.Run("SetEnabled", func(t *testing.T) {
		reg := NewEndpointRegistry()
		reg.Register(&Endpoint{Slug: "test-ep", Enabled: true})

		// Disable
		ok := reg.SetEnabled("test-ep", false)
		if !ok {
			t.Error("SetEnabled should return true for existing endpoint")
		}

		ep, _ := reg.Get("test-ep")
		if ep.Enabled {
			t.Error("endpoint should be disabled")
		}

		// Enable
		ok = reg.SetEnabled("test-ep", true)
		if !ok {
			t.Error("SetEnabled should return true")
		}

		ep, _ = reg.Get("test-ep")
		if !ep.Enabled {
			t.Error("endpoint should be enabled")
		}

		// Non-existent
		ok = reg.SetEnabled("non-existent", true)
		if ok {
			t.Error("SetEnabled should return false for non-existent endpoint")
		}
	})
}

func TestEndpointRegistryConcurrency(t *testing.T) {
	reg := NewEndpointRegistry()
	var wg sync.WaitGroup

	// Concurrent writes
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			slug := "ep" + string(rune('a'+n%26))
			reg.Register(&Endpoint{Slug: slug})
		}(i)
	}

	// Concurrent reads
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			reg.List()
		}()
	}

	// Concurrent SetEnabled
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			slug := "ep" + string(rune('a'+n%26))
			reg.SetEnabled(slug, n%2 == 0)
		}(i)
	}

	wg.Wait()

	// Should not panic and registry should be consistent
	list := reg.List()
	if len(list) == 0 {
		t.Error("registry should have some endpoints after concurrent operations")
	}
}

func TestDataSourceBuilder(t *testing.T) {
	t.Run("empty name error", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Type: EndpointTypeDataSource}},
		}

		builder.Name("")
		if builder.err == nil {
			t.Error("expected error for empty name")
		}
	})

	t.Run("empty description error", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Type: EndpointTypeDataSource}},
		}

		builder.Description("")
		if builder.err == nil {
			t.Error("expected error for empty description")
		}
	})

	t.Run("error propagation", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test"}, err: errors.New("previous error")},
		}

		// All methods should return early on error
		builder.Name("Test").Description("Desc").Version("1.0").Enabled(true)

		// Error should still be the original
		if builder.err.Error() != "previous error" {
			t.Error("error should propagate")
		}
	})

	t.Run("Version does not require value", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test"}},
		}

		builder.Version("2.0.0")
		if builder.err != nil {
			t.Errorf("Version should not error: %v", builder.err)
		}
		if builder.endpoint.Version != "2.0.0" {
			t.Errorf("Version = %q", builder.endpoint.Version)
		}
	})

	t.Run("Enabled sets value", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test"}},
		}

		builder.Enabled(false)
		if builder.err != nil {
			t.Errorf("Enabled should not error: %v", builder.err)
		}
		if builder.endpoint.Enabled {
			t.Error("Enabled should be false")
		}
	})

	t.Run("Handler requires handler", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Name: "Test", Description: "Test desc"}},
		}

		err := builder.Handler(nil)
		if err == nil {
			t.Error("expected error for nil handler")
		}
	})

	t.Run("Handler requires name", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Description: "Desc"}},
		}

		err := builder.Handler(func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
			return nil, nil
		})
		if err == nil {
			t.Error("expected error for missing name")
		}
	})

	t.Run("Handler requires description", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Name: "Test"}},
		}

		err := builder.Handler(func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
			return nil, nil
		})
		if err == nil {
			t.Error("expected error for missing description")
		}
	})

	t.Run("Handler returns previous error", func(t *testing.T) {
		builder := &DataSourceBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test"}, err: errors.New("builder error")},
		}

		err := builder.Handler(func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
			return nil, nil
		})
		if err == nil || err.Error() != "builder error" {
			t.Error("Handler should return previous error")
		}
	})
}

func TestModelBuilder(t *testing.T) {
	t.Run("empty name error", func(t *testing.T) {
		builder := &ModelBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Type: EndpointTypeModel}},
		}

		builder.Name("")
		if builder.err == nil {
			t.Error("expected error for empty name")
		}
	})

	t.Run("empty description error", func(t *testing.T) {
		builder := &ModelBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Type: EndpointTypeModel}},
		}

		builder.Description("")
		if builder.err == nil {
			t.Error("expected error for empty description")
		}
	})

	t.Run("error propagation", func(t *testing.T) {
		builder := &ModelBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test"}, err: errors.New("previous error")},
		}

		builder.Name("Test").Description("Desc").Version("1.0").Enabled(true)

		if builder.err.Error() != "previous error" {
			t.Error("error should propagate")
		}
	})

	t.Run("Handler requires handler", func(t *testing.T) {
		builder := &ModelBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Name: "Test", Description: "Desc"}},
		}

		err := builder.Handler(nil)
		if err == nil {
			t.Error("expected error for nil handler")
		}
	})

	t.Run("Handler requires name", func(t *testing.T) {
		builder := &ModelBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Description: "Desc"}},
		}

		err := builder.Handler(func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
			return "", nil
		})
		if err == nil {
			t.Error("expected error for missing name")
		}
	})

	t.Run("Handler requires description", func(t *testing.T) {
		builder := &ModelBuilder{
			baseEndpointBuilder: baseEndpointBuilder{endpoint: &Endpoint{Slug: "test", Name: "Test"}},
		}

		err := builder.Handler(func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
			return "", nil
		})
		if err == nil {
			t.Error("expected error for missing description")
		}
	})
}
