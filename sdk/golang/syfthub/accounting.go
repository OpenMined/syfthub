package syfthub

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// AccountingResource handles accounting/billing operations with external service.
//
// The accounting service manages user balances and transactions. It uses
// Basic auth (email/password) for authentication, which is separate from
// SyftHub's JWT-based authentication.
//
// Credentials are automatically retrieved from the backend after login.
// Users don't need to configure accounting credentials manually.
//
// Transaction Workflow:
//  1. Sender creates transaction (status=PENDING)
//  2. Either party confirms (status=COMPLETED) or cancels (status=CANCELLED)
//
// Delegated Transaction Workflow:
//  1. Sender creates a transaction token for recipient
//  2. Recipient uses token to create delegated transaction
//  3. Recipient confirms the transaction
//
// Example usage:
//
//	// Login first
//	client, _ := syfthub.NewClient()
//	client.Auth.Login(ctx, "user@example.com", "password")
//
//	// Get accounting resource (auto-fetches credentials)
//	accounting, err := client.Accounting(ctx)
//
//	// Get current user info
//	user, err := accounting.GetUser(ctx)
//	fmt.Printf("Balance: %f\n", user.Balance)
//
//	// Create a transaction
//	tx, err := accounting.CreateTransaction(ctx, &CreateTransactionRequest{
//	    RecipientEmail: "recipient@example.com",
//	    Amount:         10.0,
//	    AppName:        "syftai-space",
//	    AppEpPath:      "alice/my-model",
//	})
//
//	// Confirm the transaction
//	tx, err = accounting.ConfirmTransaction(ctx, tx.ID)
type AccountingResource struct {
	http    *httpClient
	timeout time.Duration
}

// newAccountingResource creates a new AccountingResource backed by the unified
// httpClient with a basicAuth strategy.
func newAccountingResource(accountingURL, email, password string, timeout time.Duration) *AccountingResource {
	return &AccountingResource{
		http:    newBasicAuthClient(accountingURL, timeout, email, password),
		timeout: timeout,
	}
}

// do makes a request through the accounting httpClient. When applyAuth is nil,
// the client's default basic-auth strategy is used; supply a closure to override
// (e.g. for delegated transactions that authenticate with a Bearer token).
func (a *AccountingResource) do(ctx context.Context, method, path string, body, result interface{}, applyAuth func(*http.Request)) error {
	var opts []RequestOption
	if applyAuth != nil {
		opts = append(opts, withAuthFunc(applyAuth))
	}
	respBody, err := a.http.Request(ctx, method, path, body, opts...)
	if err != nil {
		return err
	}
	if result != nil && len(respBody) > 0 {
		return json.Unmarshal(respBody, result)
	}
	return nil
}

// request makes a request with the default basic-auth strategy.
func (a *AccountingResource) request(ctx context.Context, method, path string, body, result interface{}) error {
	return a.do(ctx, method, path, body, result, nil)
}

// requestWithToken makes a request authenticated with a Bearer token (used for
// delegated transactions). It shares the httpClient connection pool.
func (a *AccountingResource) requestWithToken(ctx context.Context, method, path, token string, body, result interface{}) error {
	return a.do(ctx, method, path, body, result, func(r *http.Request) {
		r.Header.Set("Authorization", "Bearer "+token)
	})
}

// =========================================================================
// User Operations
// =========================================================================

// GetUser returns the current user's account information including balance.
//
// Errors:
//   - AuthenticationError: If authentication fails
//   - APIError: On other errors
func (a *AccountingResource) GetUser(ctx context.Context) (*AccountingUser, error) {
	var user AccountingUser
	err := a.request(ctx, "GET", "/user", nil, &user)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

// UpdatePassword updates the user's password.
//
// Errors:
//   - AuthenticationError: If current password is wrong
//   - ValidationError: If new password doesn't meet requirements
func (a *AccountingResource) UpdatePassword(ctx context.Context, currentPassword, newPassword string) error {
	return a.request(ctx, "PUT", "/user/password", map[string]string{
		"oldPassword": currentPassword,
		"newPassword": newPassword,
	}, nil)
}

// UpdateOrganization updates the user's organization.
//
// Errors:
//   - AuthenticationError: If authentication fails
func (a *AccountingResource) UpdateOrganization(ctx context.Context, organization string) error {
	return a.request(ctx, "PUT", "/user/organization", map[string]string{
		"organization": organization,
	}, nil)
}

// =========================================================================
// Transaction Listing
// =========================================================================

// GetTransactionsOption configures the GetTransactions operation.
type GetTransactionsOption func(*getTransactionsOptions)

type getTransactionsOptions struct {
	pageSize int
}

// WithTransactionsPageSize sets the page size for listing transactions.
func WithTransactionsPageSize(size int) GetTransactionsOption {
	return func(o *getTransactionsOptions) {
		o.pageSize = size
	}
}

// GetTransactions returns a paginated list of transactions.
//
// Errors:
//   - AuthenticationError: If authentication fails
func (a *AccountingResource) GetTransactions(ctx context.Context, opts ...GetTransactionsOption) *PageIterator[Transaction] {
	options := &getTransactionsOptions{pageSize: 20}
	for _, opt := range opts {
		opt(options)
	}

	fetchFn := func(ctx context.Context, skip, limit int) ([]json.RawMessage, error) {
		query := url.Values{}
		query.Set("skip", strconv.Itoa(skip))
		query.Set("limit", strconv.Itoa(limit))

		var transactions []json.RawMessage
		err := a.request(ctx, "GET", "/transactions?"+query.Encode(), nil, &transactions)
		if err != nil {
			return nil, err
		}
		return transactions, nil
	}

	return NewPageIterator[Transaction](fetchFn, options.pageSize)
}

// GetTransaction returns a specific transaction by ID.
//
// Errors:
//   - NotFoundError: If transaction not found
//   - AuthenticationError: If authentication fails
func (a *AccountingResource) GetTransaction(ctx context.Context, transactionID string) (*Transaction, error) {
	var tx Transaction
	err := a.request(ctx, "GET", fmt.Sprintf("/transactions/%s", transactionID), nil, &tx)
	if err != nil {
		return nil, err
	}
	return &tx, nil
}

// =========================================================================
// Direct Transaction Operations
// =========================================================================

// CreateTransactionRequest contains parameters for creating a transaction.
type CreateTransactionRequest struct {
	// RecipientEmail is the email of the recipient
	RecipientEmail string

	// Amount is the amount to transfer (must be > 0)
	Amount float64

	// AppName is an optional app name for context (e.g., "syftai-space")
	AppName string

	// AppEpPath is an optional endpoint path for context (e.g., "alice/model")
	AppEpPath string
}

// CreateTransaction creates a new transaction (direct transfer).
//
// Creates a PENDING transaction that must be confirmed or cancelled.
// The transaction is created by the sender (current user).
//
// Errors:
//   - ValidationError: If amount <= 0 or insufficient balance
//   - AuthenticationError: If authentication fails
func (a *AccountingResource) CreateTransaction(ctx context.Context, req *CreateTransactionRequest) (*Transaction, error) {
	if req.Amount <= 0 {
		return nil, newValidationError("Amount must be greater than 0", nil)
	}

	payload := map[string]interface{}{
		"recipientEmail": req.RecipientEmail,
		"amount":         req.Amount,
	}
	if req.AppName != "" {
		payload["appName"] = req.AppName
	}
	if req.AppEpPath != "" {
		payload["appEpPath"] = req.AppEpPath
	}

	var tx Transaction
	err := a.request(ctx, "POST", "/transactions", payload, &tx)
	if err != nil {
		return nil, err
	}
	return &tx, nil
}

// ConfirmTransaction confirms a pending transaction.
//
// Confirms the transaction, transferring funds from sender to recipient.
// Can be called by either the sender or recipient.
//
// Errors:
//   - NotFoundError: If transaction not found
//   - ValidationError: If transaction is not in PENDING status
//   - AuthenticationError: If authentication fails
func (a *AccountingResource) ConfirmTransaction(ctx context.Context, transactionID string) (*Transaction, error) {
	var tx Transaction
	err := a.request(ctx, "POST", fmt.Sprintf("/transactions/%s/confirm", transactionID), nil, &tx)
	if err != nil {
		return nil, err
	}
	return &tx, nil
}

// CancelTransaction cancels a pending transaction.
//
// Cancels the transaction without transferring funds.
// Can be called by either the sender or recipient.
//
// Errors:
//   - NotFoundError: If transaction not found
//   - ValidationError: If transaction is not in PENDING status
//   - AuthenticationError: If authentication fails
func (a *AccountingResource) CancelTransaction(ctx context.Context, transactionID string) (*Transaction, error) {
	var tx Transaction
	err := a.request(ctx, "POST", fmt.Sprintf("/transactions/%s/cancel", transactionID), nil, &tx)
	if err != nil {
		return nil, err
	}
	return &tx, nil
}

// =========================================================================
// Delegated Transaction Operations
// =========================================================================

// CreateTransactionToken creates a transaction token for delegated transfers.
//
// Creates a JWT token that authorizes the recipient to create a
// transaction on behalf of the sender (current user). The token
// is short-lived (typically ~5 minutes).
//
// Use this when you want to pre-authorize a payment that will be
// initiated by the recipient (e.g., a service charging for usage).
//
// Errors:
//   - AuthenticationError: If authentication fails
func (a *AccountingResource) CreateTransactionToken(ctx context.Context, recipientEmail string) (string, error) {
	var response struct {
		Token string `json:"token"`
	}
	err := a.request(ctx, "POST", "/token/create", map[string]string{
		"recipientEmail": recipientEmail,
	}, &response)
	if err != nil {
		return "", err
	}
	return response.Token, nil
}

// CreateDelegatedTransactionRequest contains parameters for creating a delegated transaction.
type CreateDelegatedTransactionRequest struct {
	// SenderEmail is the email of the sender who created the token
	SenderEmail string

	// Amount is the amount to transfer (must be > 0)
	Amount float64

	// Token is the JWT token from sender's CreateTransactionToken()
	Token string
}

// CreateDelegatedTransaction creates a delegated transaction using a pre-authorized token.
//
// Creates a transaction on behalf of the sender using their token.
// This is typically used by services to charge users for usage.
//
// The token authenticates the request instead of Basic auth.
//
// Errors:
//   - AuthenticationError: If token is invalid or expired
//   - ValidationError: If amount <= 0
func (a *AccountingResource) CreateDelegatedTransaction(ctx context.Context, req *CreateDelegatedTransactionRequest) (*Transaction, error) {
	if req.Amount <= 0 {
		return nil, newValidationError("Amount must be greater than 0", nil)
	}

	var tx Transaction
	err := a.requestWithToken(ctx, "POST", "/transactions", req.Token, map[string]interface{}{
		"senderEmail": req.SenderEmail,
		"amount":      req.Amount,
	}, &tx)
	if err != nil {
		return nil, err
	}
	return &tx, nil
}

// Close closes the HTTP client and releases resources.
func (a *AccountingResource) Close() {
	if a.http != nil {
		a.http.Close()
	}
}
