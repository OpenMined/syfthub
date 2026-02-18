package syfthub

import (
	"encoding/json"
	"testing"
	"time"
)

func TestVisibilityEnum(t *testing.T) {
	testCases := []struct {
		value Visibility
		str   string
	}{
		{VisibilityPublic, "public"},
		{VisibilityPrivate, "private"},
		{VisibilityInternal, "internal"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("Visibility = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestEndpointTypeEnum(t *testing.T) {
	testCases := []struct {
		value EndpointType
		str   string
	}{
		{EndpointTypeModel, "model"},
		{EndpointTypeDataSource, "data_source"},
		{EndpointTypeModelDataSource, "model_data_source"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("EndpointType = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestUserRoleEnum(t *testing.T) {
	testCases := []struct {
		value UserRole
		str   string
	}{
		{UserRoleAdmin, "admin"},
		{UserRoleUser, "user"},
		{UserRoleGuest, "guest"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("UserRole = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestOrganizationRoleEnum(t *testing.T) {
	testCases := []struct {
		value OrganizationRole
		str   string
	}{
		{OrganizationRoleOwner, "owner"},
		{OrganizationRoleAdmin, "admin"},
		{OrganizationRoleMember, "member"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("OrganizationRole = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestTransactionStatusEnum(t *testing.T) {
	testCases := []struct {
		value TransactionStatus
		str   string
	}{
		{TransactionStatusPending, "pending"},
		{TransactionStatusCompleted, "completed"},
		{TransactionStatusCancelled, "cancelled"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("TransactionStatus = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestCreatorTypeEnum(t *testing.T) {
	testCases := []struct {
		value CreatorType
		str   string
	}{
		{CreatorTypeSystem, "system"},
		{CreatorTypeSender, "sender"},
		{CreatorTypeRecipient, "recipient"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("CreatorType = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestSourceStatusEnum(t *testing.T) {
	testCases := []struct {
		value SourceStatus
		str   string
	}{
		{SourceStatusSuccess, "success"},
		{SourceStatusError, "error"},
		{SourceStatusTimeout, "timeout"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("SourceStatus = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestAPITokenScopeEnum(t *testing.T) {
	testCases := []struct {
		value APITokenScope
		str   string
	}{
		{APITokenScopeRead, "read"},
		{APITokenScopeWrite, "write"},
		{APITokenScopeFull, "full"},
	}

	for _, tc := range testCases {
		t.Run(tc.str, func(t *testing.T) {
			if string(tc.value) != tc.str {
				t.Errorf("APITokenScope = %q, want %q", string(tc.value), tc.str)
			}
		})
	}
}

func TestUserJSON(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	avatar := "https://example.com/avatar.png"
	domain := "example.com"
	aggURL := "https://agg.example.com"

	user := User{
		ID:            1,
		Username:      "testuser",
		Email:         "test@example.com",
		FullName:      "Test User",
		AvatarURL:     &avatar,
		Role:          UserRoleUser,
		IsActive:      true,
		CreatedAt:     now,
		UpdatedAt:     &now,
		Domain:        &domain,
		AggregatorURL: &aggURL,
	}

	data, err := json.Marshal(user)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded User
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.ID != user.ID {
		t.Errorf("ID = %d, want %d", decoded.ID, user.ID)
	}
	if decoded.Username != user.Username {
		t.Errorf("Username = %q", decoded.Username)
	}
	if decoded.Email != user.Email {
		t.Errorf("Email = %q", decoded.Email)
	}
	if decoded.Role != user.Role {
		t.Errorf("Role = %q", decoded.Role)
	}
	if decoded.AvatarURL == nil || *decoded.AvatarURL != avatar {
		t.Errorf("AvatarURL = %v", decoded.AvatarURL)
	}
}

func TestEndpointOwnerType(t *testing.T) {
	t.Run("user owned", func(t *testing.T) {
		userID := 1
		ep := Endpoint{UserID: &userID}
		if ep.OwnerType() != "user" {
			t.Errorf("OwnerType = %q, want user", ep.OwnerType())
		}
	})

	t.Run("organization owned", func(t *testing.T) {
		orgID := 1
		ep := Endpoint{OrganizationID: &orgID}
		if ep.OwnerType() != "organization" {
			t.Errorf("OwnerType = %q, want organization", ep.OwnerType())
		}
	})
}

func TestEndpointPublicPath(t *testing.T) {
	ep := EndpointPublic{
		OwnerUsername: "alice",
		Slug:          "my-model",
	}
	expected := "alice/my-model"
	if ep.Path() != expected {
		t.Errorf("Path = %q, want %q", ep.Path(), expected)
	}
}

func TestEndpointSearchResultPath(t *testing.T) {
	ep := EndpointSearchResult{
		OwnerUsername: "bob",
		Slug:          "dataset",
	}
	expected := "bob/dataset"
	if ep.Path() != expected {
		t.Errorf("Path = %q, want %q", ep.Path(), expected)
	}
}

func TestTransactionStatusMethods(t *testing.T) {
	t.Run("IsPending", func(t *testing.T) {
		tx := Transaction{Status: TransactionStatusPending}
		if !tx.IsPending() {
			t.Error("IsPending should return true")
		}
		if tx.IsCompleted() {
			t.Error("IsCompleted should return false")
		}
		if tx.IsCancelled() {
			t.Error("IsCancelled should return false")
		}
	})

	t.Run("IsCompleted", func(t *testing.T) {
		tx := Transaction{Status: TransactionStatusCompleted}
		if tx.IsPending() {
			t.Error("IsPending should return false")
		}
		if !tx.IsCompleted() {
			t.Error("IsCompleted should return true")
		}
		if tx.IsCancelled() {
			t.Error("IsCancelled should return false")
		}
	})

	t.Run("IsCancelled", func(t *testing.T) {
		tx := Transaction{Status: TransactionStatusCancelled}
		if tx.IsPending() {
			t.Error("IsPending should return false")
		}
		if tx.IsCompleted() {
			t.Error("IsCompleted should return false")
		}
		if !tx.IsCancelled() {
			t.Error("IsCancelled should return true")
		}
	})
}

func TestAuthTokensJSON(t *testing.T) {
	tokens := AuthTokens{
		AccessToken:  "access-token-123",
		RefreshToken: "refresh-token-456",
		TokenType:    "bearer",
	}

	data, err := json.Marshal(tokens)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded AuthTokens
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.AccessToken != tokens.AccessToken {
		t.Errorf("AccessToken = %q", decoded.AccessToken)
	}
	if decoded.RefreshToken != tokens.RefreshToken {
		t.Errorf("RefreshToken = %q", decoded.RefreshToken)
	}
	if decoded.TokenType != tokens.TokenType {
		t.Errorf("TokenType = %q", decoded.TokenType)
	}
}

func TestPolicyJSON(t *testing.T) {
	policy := Policy{
		Type:        "allow_list",
		Version:     "1.0",
		Enabled:     true,
		Description: "Allow specific users",
		Config: map[string]interface{}{
			"users": []string{"alice", "bob"},
		},
	}

	data, err := json.Marshal(policy)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded Policy
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Type != policy.Type {
		t.Errorf("Type = %q", decoded.Type)
	}
	if decoded.Enabled != policy.Enabled {
		t.Errorf("Enabled = %v", decoded.Enabled)
	}
}

func TestConnectionJSON(t *testing.T) {
	conn := Connection{
		Type:        "syftai_space",
		Enabled:     true,
		Description: "SyftAI Space connection",
		Config: map[string]interface{}{
			"url":         "https://space.example.com",
			"tenant_name": "default",
		},
	}

	data, err := json.Marshal(conn)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded Connection
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Type != conn.Type {
		t.Errorf("Type = %q", decoded.Type)
	}
	if decoded.Config["url"] != "https://space.example.com" {
		t.Errorf("Config[url] = %v", decoded.Config["url"])
	}
}

func TestChatEventTypes(t *testing.T) {
	testCases := []struct {
		event    ChatEvent
		expected ChatEventType
	}{
		{&RetrievalStartEvent{}, ChatEventTypeRetrievalStart},
		{&SourceCompleteEvent{}, ChatEventTypeSourceComplete},
		{&RetrievalCompleteEvent{}, ChatEventTypeRetrievalComplete},
		{&GenerationStartEvent{}, ChatEventTypeGenerationStart},
		{&TokenEvent{}, ChatEventTypeToken},
		{&DoneEvent{}, ChatEventTypeDone},
		{&ErrorEvent{}, ChatEventTypeError},
	}

	for _, tc := range testCases {
		t.Run(string(tc.expected), func(t *testing.T) {
			if tc.event.EventType() != tc.expected {
				t.Errorf("EventType = %q, want %q", tc.event.EventType(), tc.expected)
			}
		})
	}
}

func TestMessageJSON(t *testing.T) {
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

	if decoded.Role != msg.Role {
		t.Errorf("Role = %q", decoded.Role)
	}
	if decoded.Content != msg.Content {
		t.Errorf("Content = %q", decoded.Content)
	}
}

func TestAPITokenJSON(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	lastIP := "192.168.1.1"

	token := APIToken{
		ID:          1,
		Name:        "CI Token",
		TokenPrefix: "syft_pat_abc",
		Scopes:      []APITokenScope{APITokenScopeRead, APITokenScopeWrite},
		ExpiresAt:   &now,
		LastUsedAt:  &now,
		LastUsedIP:  &lastIP,
		IsActive:    true,
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	data, err := json.Marshal(token)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded APIToken
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.ID != token.ID {
		t.Errorf("ID = %d", decoded.ID)
	}
	if decoded.Name != token.Name {
		t.Errorf("Name = %q", decoded.Name)
	}
	if len(decoded.Scopes) != 2 {
		t.Errorf("Scopes length = %d", len(decoded.Scopes))
	}
	if decoded.LastUsedIP == nil || *decoded.LastUsedIP != lastIP {
		t.Errorf("LastUsedIP = %v", decoded.LastUsedIP)
	}
}

func TestChatResponseJSON(t *testing.T) {
	resp := ChatResponse{
		Response: "This is the response",
		Sources: map[string]DocumentSource{
			"doc1": {Slug: "my-dataset", Content: "Source content"},
		},
		RetrievalInfo: []SourceInfo{
			{Path: "alice/dataset", DocumentsRetrieved: 5, Status: SourceStatusSuccess},
		},
		Metadata: ChatMetadata{
			RetrievalTimeMs:  100,
			GenerationTimeMs: 500,
			TotalTimeMs:      600,
		},
		Usage: &TokenUsage{
			PromptTokens:     50,
			CompletionTokens: 100,
			TotalTokens:      150,
		},
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded ChatResponse
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Response != resp.Response {
		t.Errorf("Response = %q", decoded.Response)
	}
	if decoded.Usage.TotalTokens != 150 {
		t.Errorf("Usage.TotalTokens = %d", decoded.Usage.TotalTokens)
	}
}

func TestPaginatedResponseJSON(t *testing.T) {
	resp := PaginatedResponse[string]{
		Items:      []string{"a", "b", "c"},
		Total:      100,
		Page:       1,
		Size:       3,
		TotalPages: 34,
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded PaginatedResponse[string]
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if len(decoded.Items) != 3 {
		t.Errorf("Items length = %d", len(decoded.Items))
	}
	if decoded.Total != 100 {
		t.Errorf("Total = %d", decoded.Total)
	}
	if decoded.TotalPages != 34 {
		t.Errorf("TotalPages = %d", decoded.TotalPages)
	}
}

func TestUserAggregatorJSON(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	agg := UserAggregator{
		ID:        1,
		UserID:    42,
		Name:      "My Aggregator",
		URL:       "https://aggregator.example.com",
		IsDefault: true,
		CreatedAt: now,
		UpdatedAt: now,
	}

	data, err := json.Marshal(agg)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded UserAggregator
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Name != agg.Name {
		t.Errorf("Name = %q", decoded.Name)
	}
	if decoded.URL != agg.URL {
		t.Errorf("URL = %q", decoded.URL)
	}
	if !decoded.IsDefault {
		t.Error("IsDefault should be true")
	}
}

func TestEndpointRefJSON(t *testing.T) {
	tenantName := "tenant1"
	owner := "alice"
	ref := EndpointRef{
		URL:           "https://space.example.com",
		Slug:          "my-model",
		Name:          "My Model",
		TenantName:    &tenantName,
		OwnerUsername: &owner,
	}

	data, err := json.Marshal(ref)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded EndpointRef
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.URL != ref.URL {
		t.Errorf("URL = %q", decoded.URL)
	}
	if decoded.Slug != ref.Slug {
		t.Errorf("Slug = %q", decoded.Slug)
	}
	if decoded.TenantName == nil || *decoded.TenantName != tenantName {
		t.Errorf("TenantName = %v", decoded.TenantName)
	}
}

func TestDocumentJSON(t *testing.T) {
	doc := Document{
		Content: "This is the document content",
		Score:   0.95,
		Metadata: map[string]interface{}{
			"source": "file.pdf",
			"page":   1,
		},
	}

	data, err := json.Marshal(doc)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded Document
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Content != doc.Content {
		t.Errorf("Content = %q", decoded.Content)
	}
	if decoded.Score != doc.Score {
		t.Errorf("Score = %f", decoded.Score)
	}
}

func TestHeartbeatResponseJSON(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	resp := HeartbeatResponse{
		Status:     "ok",
		ReceivedAt: now,
		ExpiresAt:  now.Add(5 * time.Minute),
		Domain:     "space.example.com",
		TTLSeconds: 300,
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded HeartbeatResponse
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Status != "ok" {
		t.Errorf("Status = %q", decoded.Status)
	}
	if decoded.TTLSeconds != 300 {
		t.Errorf("TTLSeconds = %d", decoded.TTLSeconds)
	}
}

func TestAccountingUserJSON(t *testing.T) {
	org := "Acme Corp"
	user := AccountingUser{
		ID:           "user-123",
		Email:        "user@example.com",
		Balance:      100.50,
		Organization: &org,
	}

	data, err := json.Marshal(user)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded AccountingUser
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.ID != user.ID {
		t.Errorf("ID = %q", decoded.ID)
	}
	if decoded.Balance != user.Balance {
		t.Errorf("Balance = %f", decoded.Balance)
	}
	if decoded.Organization == nil || *decoded.Organization != org {
		t.Errorf("Organization = %v", decoded.Organization)
	}
}

func TestSyncEndpointsResponseJSON(t *testing.T) {
	resp := SyncEndpointsResponse{
		Synced:  5,
		Deleted: 2,
		Endpoints: []Endpoint{
			{ID: 1, Name: "Endpoint 1"},
			{ID: 2, Name: "Endpoint 2"},
		},
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded SyncEndpointsResponse
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Synced != 5 {
		t.Errorf("Synced = %d", decoded.Synced)
	}
	if decoded.Deleted != 2 {
		t.Errorf("Deleted = %d", decoded.Deleted)
	}
	if len(decoded.Endpoints) != 2 {
		t.Errorf("Endpoints length = %d", len(decoded.Endpoints))
	}
}
