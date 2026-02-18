package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestNewAccountingResource(t *testing.T) {
	ar := newAccountingResource("https://accounting.example.com/", "user@example.com", "password123", 30*time.Second)

	if ar.url != "https://accounting.example.com" {
		t.Errorf("url = %q, trailing slash should be trimmed", ar.url)
	}
	if ar.email != "user@example.com" {
		t.Errorf("email = %q", ar.email)
	}
	if ar.password != "password123" {
		t.Errorf("password = %q", ar.password)
	}
	if ar.timeout != 30*time.Second {
		t.Errorf("timeout = %v", ar.timeout)
	}
	if ar.client == nil {
		t.Error("client should be initialized")
	}
}

func TestAccountingResourceGetUser(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/user" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "GET" {
			t.Errorf("method = %s", r.Method)
		}

		// Verify Basic auth
		user, pass, ok := r.BasicAuth()
		if !ok {
			t.Error("Basic auth not set")
		}
		if user != "test@example.com" || pass != "testpass" {
			t.Errorf("auth = %s:%s", user, pass)
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":           "user123",
			"email":        "test@example.com",
			"balance":      100.50,
			"organization": "Test Org",
		})
	}))
	defer server.Close()

	ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

	user, err := ar.GetUser(context.Background())
	if err != nil {
		t.Fatalf("GetUser error: %v", err)
	}
	if user.Email != "test@example.com" {
		t.Errorf("Email = %q", user.Email)
	}
	if user.Balance != 100.50 {
		t.Errorf("Balance = %f", user.Balance)
	}
}

func TestAccountingResourceUpdatePassword(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/user/password" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "PUT" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]string
			json.NewDecoder(r.Body).Decode(&body)

			if body["oldPassword"] != "oldpass" {
				t.Errorf("oldPassword = %v", body["oldPassword"])
			}
			if body["newPassword"] != "newpass" {
				t.Errorf("newPassword = %v", body["newPassword"])
			}

			w.WriteHeader(http.StatusNoContent)
		}))
		defer server.Close()

		ar := newAccountingResource(server.URL, "test@example.com", "oldpass", DefaultTimeout)

		err := ar.UpdatePassword(context.Background(), "oldpass", "newpass")
		if err != nil {
			t.Fatalf("UpdatePassword error: %v", err)
		}
	})

	t.Run("wrong password", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Invalid password"})
		}))
		defer server.Close()

		ar := newAccountingResource(server.URL, "test@example.com", "wrongpass", DefaultTimeout)

		err := ar.UpdatePassword(context.Background(), "wrongpass", "newpass")
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*AuthenticationError)
		if !ok {
			t.Fatalf("expected AuthenticationError, got %T", err)
		}
	})
}

func TestAccountingResourceUpdateOrganization(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/user/organization" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "PUT" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]string
		json.NewDecoder(r.Body).Decode(&body)

		if body["organization"] != "New Org" {
			t.Errorf("organization = %v", body["organization"])
		}

		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

	err := ar.UpdateOrganization(context.Background(), "New Org")
	if err != nil {
		t.Fatalf("UpdateOrganization error: %v", err)
	}
}

func TestAccountingResourceGetTransactions(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/transactions") {
			t.Errorf("path = %s", r.URL.Path)
		}

		requestCount++

		if requestCount == 1 {
			// First page
			json.NewEncoder(w).Encode([]map[string]interface{}{
				{"id": "tx1", "amount": 10.0, "status": "COMPLETED"},
				{"id": "tx2", "amount": 20.0, "status": "PENDING"},
			})
		} else {
			// Empty second page
			json.NewEncoder(w).Encode([]map[string]interface{}{})
		}
	}))
	defer server.Close()

	ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

	iter := ar.GetTransactions(context.Background(), WithTransactionsPageSize(2))

	var collected []Transaction
	for iter.Next(context.Background()) {
		collected = append(collected, iter.Value())
	}

	if err := iter.Err(); err != nil {
		t.Fatalf("iterator error: %v", err)
	}

	if len(collected) != 2 {
		t.Errorf("collected = %d", len(collected))
	}
}

func TestAccountingResourceGetTransaction(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/transactions/tx123" {
				t.Errorf("path = %s", r.URL.Path)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":             "tx123",
				"sender_email":   "sender@example.com",
				"receiver_email": "receiver@example.com",
				"amount":         50.0,
				"status":         "COMPLETED",
			})
		}))
		defer server.Close()

		ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

		tx, err := ar.GetTransaction(context.Background(), "tx123")
		if err != nil {
			t.Fatalf("GetTransaction error: %v", err)
		}
		if tx.ID != "tx123" {
			t.Errorf("ID = %q", tx.ID)
		}
		if tx.Amount != 50.0 {
			t.Errorf("Amount = %f", tx.Amount)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Transaction not found"})
		}))
		defer server.Close()

		ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

		_, err := ar.GetTransaction(context.Background(), "nonexistent")
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
	})
}

func TestAccountingResourceCreateTransaction(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/transactions" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["recipientEmail"] != "recipient@example.com" {
				t.Errorf("recipientEmail = %v", body["recipientEmail"])
			}
			if body["amount"].(float64) != 25.0 {
				t.Errorf("amount = %v", body["amount"])
			}
			if body["appName"] != "syftai-space" {
				t.Errorf("appName = %v", body["appName"])
			}
			if body["appEpPath"] != "alice/model" {
				t.Errorf("appEpPath = %v", body["appEpPath"])
			}

			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":             "tx_new",
				"sender_email":   "test@example.com",
				"receiver_email": "recipient@example.com",
				"amount":         25.0,
				"status":         "PENDING",
			})
		}))
		defer server.Close()

		ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

		tx, err := ar.CreateTransaction(context.Background(), &CreateTransactionRequest{
			RecipientEmail: "recipient@example.com",
			Amount:         25.0,
			AppName:        "syftai-space",
			AppEpPath:      "alice/model",
		})
		if err != nil {
			t.Fatalf("CreateTransaction error: %v", err)
		}
		if tx.ID != "tx_new" {
			t.Errorf("ID = %q", tx.ID)
		}
		if tx.Status != "PENDING" {
			t.Errorf("Status = %q", tx.Status)
		}
	})

	t.Run("invalid amount", func(t *testing.T) {
		ar := newAccountingResource("http://localhost", "test@example.com", "testpass", DefaultTimeout)

		_, err := ar.CreateTransaction(context.Background(), &CreateTransactionRequest{
			RecipientEmail: "recipient@example.com",
			Amount:         0,
		})
		if err == nil {
			t.Fatal("expected error for zero amount")
		}
		_, ok := err.(*ValidationError)
		if !ok {
			t.Fatalf("expected ValidationError, got %T", err)
		}
	})

	t.Run("negative amount", func(t *testing.T) {
		ar := newAccountingResource("http://localhost", "test@example.com", "testpass", DefaultTimeout)

		_, err := ar.CreateTransaction(context.Background(), &CreateTransactionRequest{
			RecipientEmail: "recipient@example.com",
			Amount:         -10.0,
		})
		if err == nil {
			t.Fatal("expected error for negative amount")
		}
	})
}

func TestAccountingResourceConfirmTransaction(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/transactions/tx123/confirm" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":     "tx123",
			"status": "COMPLETED",
		})
	}))
	defer server.Close()

	ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

	tx, err := ar.ConfirmTransaction(context.Background(), "tx123")
	if err != nil {
		t.Fatalf("ConfirmTransaction error: %v", err)
	}
	if tx.Status != "COMPLETED" {
		t.Errorf("Status = %q", tx.Status)
	}
}

func TestAccountingResourceCancelTransaction(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/transactions/tx123/cancel" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":     "tx123",
			"status": "CANCELLED",
		})
	}))
	defer server.Close()

	ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

	tx, err := ar.CancelTransaction(context.Background(), "tx123")
	if err != nil {
		t.Fatalf("CancelTransaction error: %v", err)
	}
	if tx.Status != "CANCELLED" {
		t.Errorf("Status = %q", tx.Status)
	}
}

func TestAccountingResourceCreateTransactionToken(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/token/create" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]string
		json.NewDecoder(r.Body).Decode(&body)

		if body["recipientEmail"] != "recipient@example.com" {
			t.Errorf("recipientEmail = %v", body["recipientEmail"])
		}

		json.NewEncoder(w).Encode(map[string]string{
			"token": "jwt_token_123",
		})
	}))
	defer server.Close()

	ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

	token, err := ar.CreateTransactionToken(context.Background(), "recipient@example.com")
	if err != nil {
		t.Fatalf("CreateTransactionToken error: %v", err)
	}
	if token != "jwt_token_123" {
		t.Errorf("token = %q", token)
	}
}

func TestAccountingResourceCreateDelegatedTransaction(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/transactions" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			// Verify Bearer token auth
			auth := r.Header.Get("Authorization")
			if auth != "Bearer delegated_token" {
				t.Errorf("Authorization = %q", auth)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["senderEmail"] != "sender@example.com" {
				t.Errorf("senderEmail = %v", body["senderEmail"])
			}
			if body["amount"].(float64) != 15.0 {
				t.Errorf("amount = %v", body["amount"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":             "tx_delegated",
				"sender_email":   "sender@example.com",
				"receiver_email": "recipient@example.com",
				"amount":         15.0,
				"status":         "PENDING",
			})
		}))
		defer server.Close()

		ar := newAccountingResource(server.URL, "recipient@example.com", "pass", DefaultTimeout)

		tx, err := ar.CreateDelegatedTransaction(context.Background(), &CreateDelegatedTransactionRequest{
			SenderEmail: "sender@example.com",
			Amount:      15.0,
			Token:       "delegated_token",
		})
		if err != nil {
			t.Fatalf("CreateDelegatedTransaction error: %v", err)
		}
		if tx.ID != "tx_delegated" {
			t.Errorf("ID = %q", tx.ID)
		}
	})

	t.Run("invalid amount", func(t *testing.T) {
		ar := newAccountingResource("http://localhost", "test@example.com", "testpass", DefaultTimeout)

		_, err := ar.CreateDelegatedTransaction(context.Background(), &CreateDelegatedTransactionRequest{
			SenderEmail: "sender@example.com",
			Amount:      0,
			Token:       "token",
		})
		if err == nil {
			t.Fatal("expected error for zero amount")
		}
		_, ok := err.(*ValidationError)
		if !ok {
			t.Fatalf("expected ValidationError, got %T", err)
		}
	})
}

func TestAccountingResourceClose(t *testing.T) {
	ar := newAccountingResource("http://localhost", "test@example.com", "testpass", DefaultTimeout)

	// Should not panic
	ar.Close()

	// Should be safe to call multiple times
	ar.Close()
}

func TestAccountingResourceErrorHandling(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		body       string
		errorType  interface{}
	}{
		{
			name:       "401 authentication error",
			statusCode: 401,
			body:       `{"detail": "Invalid credentials"}`,
			errorType:  &AuthenticationError{},
		},
		{
			name:       "403 authorization error",
			statusCode: 403,
			body:       `{"detail": "Permission denied"}`,
			errorType:  &AuthorizationError{},
		},
		{
			name:       "404 not found error",
			statusCode: 404,
			body:       `{"detail": "Not found"}`,
			errorType:  &NotFoundError{},
		},
		{
			name:       "422 validation error",
			statusCode: 422,
			body:       `{"detail": "Invalid input"}`,
			errorType:  &ValidationError{},
		},
		{
			name:       "500 api error",
			statusCode: 500,
			body:       `{"detail": "Internal server error"}`,
			errorType:  &APIError{},
		},
		{
			name:       "error with message field",
			statusCode: 400,
			body:       `{"message": "Bad request message"}`,
			errorType:  &APIError{},
		},
		{
			name:       "error with invalid json",
			statusCode: 400,
			body:       `not json`,
			errorType:  &APIError{},
		},
		{
			name:       "error with empty body",
			statusCode: 400,
			body:       ``,
			errorType:  &APIError{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.statusCode)
				w.Write([]byte(tt.body))
			}))
			defer server.Close()

			ar := newAccountingResource(server.URL, "test@example.com", "testpass", DefaultTimeout)

			_, err := ar.GetUser(context.Background())
			if err == nil {
				t.Fatal("expected error")
			}

			switch tt.errorType.(type) {
			case *AuthenticationError:
				if _, ok := err.(*AuthenticationError); !ok {
					t.Errorf("expected AuthenticationError, got %T", err)
				}
			case *AuthorizationError:
				if _, ok := err.(*AuthorizationError); !ok {
					t.Errorf("expected AuthorizationError, got %T", err)
				}
			case *NotFoundError:
				if _, ok := err.(*NotFoundError); !ok {
					t.Errorf("expected NotFoundError, got %T", err)
				}
			case *ValidationError:
				if _, ok := err.(*ValidationError); !ok {
					t.Errorf("expected ValidationError, got %T", err)
				}
			case *APIError:
				if _, ok := err.(*APIError); !ok {
					t.Errorf("expected APIError, got %T", err)
				}
			}
		})
	}
}

func TestWithTransactionsPageSize(t *testing.T) {
	opts := &getTransactionsOptions{pageSize: 20}
	WithTransactionsPageSize(50)(opts)
	if opts.pageSize != 50 {
		t.Errorf("pageSize = %d, want 50", opts.pageSize)
	}
}
