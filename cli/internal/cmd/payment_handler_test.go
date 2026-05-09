package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

// withInjectedHelpers swaps the package-level injection points and returns a
// restore func. Keeps each test hermetic.
func withInjectedHelpers(
	t *testing.T,
	stdin io.Reader,
	stdout io.Writer,
	pp func(string) (string, error),
	wallet func(string) (any, error),
	sign func(context.Context, string, any, string) (string, string, error),
	post func(context.Context, string, string, []byte) error,
) func() {
	t.Helper()
	origStdin := paymentStdin
	origStdout := paymentStdout
	origPP := promptPassphrase
	origWallet := loadAndDecryptWallet
	origSign := signCredential
	origPost := httpPostCredential

	if stdin != nil {
		paymentStdin = stdin
	}
	if stdout != nil {
		paymentStdout = stdout
	}
	if pp != nil {
		promptPassphrase = pp
	}
	if wallet != nil {
		loadAndDecryptWallet = wallet
	}
	if sign != nil {
		signCredential = sign
	}
	if post != nil {
		httpPostCredential = post
	}

	return func() {
		paymentStdin = origStdin
		paymentStdout = origStdout
		promptPassphrase = origPP
		loadAndDecryptWallet = origWallet
		signCredential = origSign
		httpPostCredential = origPost
	}
}

func sampleEvent() PaymentRequiredEvent {
	return PaymentRequiredEvent{
		ChatSessionID: "sess-123",
		EndpointSlug:  "alice/paid-model",
		Challenge:     "0xchallenge",
		Amount:        "0.05",
		Currency:      "PathUSD",
		Recipient:     "0xRecipient",
		ChallengeID:   "ch-abc",
		Intent:        "chat.completion",
		RPCURL:        "https://rpc.tempo.example",
	}
}

// TestHandlePaymentRequired_JSONMode asserts that --json mode emits the event
// payload to stdout and returns nil without prompting or touching the wallet.
func TestHandlePaymentRequired_JSONMode(t *testing.T) {
	walletCalled := false
	signCalled := false
	postCalled := false
	stdout := &bytes.Buffer{}

	restore := withInjectedHelpers(t,
		strings.NewReader(""), // stdin should never be read
		// Note: output.JSON writes to os.Stdout directly via fmt.Println,
		// so we redirect os.Stdout for this test alone.
		stdout,
		func(string) (string, error) {
			t.Fatal("promptPassphrase must not be called in JSON mode")
			return "", nil
		},
		func(string) (any, error) {
			walletCalled = true
			return nil, nil
		},
		func(context.Context, string, any, string) (string, string, error) {
			signCalled = true
			return "", "", nil
		},
		func(context.Context, string, string, []byte) error {
			postCalled = true
			return nil
		},
	)
	defer restore()

	// output.JSON writes to os.Stdout via fmt — capture it.
	captured := captureStdout(t, func() {
		err := HandlePaymentRequired(
			context.Background(),
			true, // jsonMode
			"https://aggregator.example",
			"api-token",
			"sess-123",
			"https://default-rpc.example",
			sampleEvent(),
		)
		if err != nil {
			t.Fatalf("HandlePaymentRequired returned error: %v", err)
		}
	})

	if walletCalled || signCalled || postCalled {
		t.Errorf("wallet/sign/post unexpectedly called in JSON mode: wallet=%v sign=%v post=%v",
			walletCalled, signCalled, postCalled)
	}

	// Captured stdout should be valid JSON containing the event fields.
	var got map[string]any
	if err := json.Unmarshal([]byte(captured), &got); err != nil {
		t.Fatalf("captured stdout is not valid JSON: %v\nraw=%q", err, captured)
	}
	if got["event"] != "payment_required" {
		t.Errorf("event field = %v, want payment_required", got["event"])
	}
	if got["challenge_id"] != "ch-abc" {
		t.Errorf("challenge_id = %v, want ch-abc", got["challenge_id"])
	}
	if got["endpoint_slug"] != "alice/paid-model" {
		t.Errorf("endpoint_slug = %v, want alice/paid-model", got["endpoint_slug"])
	}
}

// TestHandlePaymentRequired_InteractiveDenied asserts that answering "n" at
// the approval prompt returns ErrPaymentDeclined and does NOT touch the
// wallet or HTTP client.
func TestHandlePaymentRequired_InteractiveDenied(t *testing.T) {
	walletCalled := false
	signCalled := false
	postCalled := false

	stdout := &bytes.Buffer{}
	restore := withInjectedHelpers(t,
		strings.NewReader("n\n"),
		stdout,
		func(string) (string, error) {
			t.Fatal("promptPassphrase must not be called when user declines")
			return "", nil
		},
		func(string) (any, error) {
			walletCalled = true
			return nil, nil
		},
		func(context.Context, string, any, string) (string, string, error) {
			signCalled = true
			return "", "", nil
		},
		func(context.Context, string, string, []byte) error {
			postCalled = true
			return nil
		},
	)
	defer restore()

	err := HandlePaymentRequired(
		context.Background(),
		false,
		"https://aggregator.example",
		"api-token",
		"sess-123",
		"https://default-rpc.example",
		sampleEvent(),
	)
	if !errors.Is(err, ErrPaymentDeclined) {
		t.Fatalf("expected ErrPaymentDeclined, got %v", err)
	}
	if walletCalled || signCalled || postCalled {
		t.Errorf("wallet/sign/post unexpectedly called after denial: wallet=%v sign=%v post=%v",
			walletCalled, signCalled, postCalled)
	}
	if !strings.Contains(stdout.String(), "Payment declined") {
		t.Errorf("expected 'Payment declined' in stdout, got: %q", stdout.String())
	}
}

// TestHandlePaymentRequired_InteractiveApproved drives the full happy path:
// "y\n" approval, mocked wallet + sign, and a real httptest server to
// validate the POST body shape.
func TestHandlePaymentRequired_InteractiveApproved(t *testing.T) {
	stdout := &bytes.Buffer{}

	var gotURL string
	var gotAuth string
	var gotBody []byte
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotURL = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		gotBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	signCalls := 0
	restore := withInjectedHelpers(t,
		strings.NewReader("y\n"),
		stdout,
		func(prompt string) (string, error) { return "secret-passphrase", nil },
		func(passphrase string) (any, error) {
			if passphrase != "secret-passphrase" {
				t.Errorf("wallet got passphrase %q, want secret-passphrase", passphrase)
			}
			return "mock-account", nil
		},
		func(_ context.Context, challenge string, account any, rpcURL string) (string, string, error) {
			signCalls++
			if challenge != "0xchallenge" {
				t.Errorf("sign got challenge %q, want 0xchallenge", challenge)
			}
			if account != "mock-account" {
				t.Errorf("sign got account %v, want mock-account", account)
			}
			if rpcURL != "https://rpc.tempo.example" {
				t.Errorf("sign got rpcURL %q, want event override", rpcURL)
			}
			return "0xCREDENTIAL", "0xTXHASH", nil
		},
		// Use the real HTTP client against httptest — restore stub afterwards.
		nil,
	)
	defer restore()

	err := HandlePaymentRequired(
		context.Background(),
		false,
		server.URL,
		"api-token",
		"sess-123",
		"https://default-rpc.example",
		sampleEvent(),
	)
	if err != nil {
		t.Fatalf("HandlePaymentRequired returned error: %v", err)
	}
	if signCalls != 1 {
		t.Errorf("signCredential called %d times, want 1", signCalls)
	}

	if gotURL != "/chat/sess-123/payment" {
		t.Errorf("POST URL = %q, want /chat/sess-123/payment", gotURL)
	}
	if gotAuth != "Bearer api-token" {
		t.Errorf("Authorization header = %q, want Bearer api-token", gotAuth)
	}

	var body map[string]string
	if err := json.Unmarshal(gotBody, &body); err != nil {
		t.Fatalf("POST body is not JSON: %v\nraw=%q", err, gotBody)
	}
	if body["challenge_id"] != "ch-abc" {
		t.Errorf("body.challenge_id = %q, want ch-abc", body["challenge_id"])
	}
	if body["credential"] != "0xCREDENTIAL" {
		t.Errorf("body.credential = %q, want 0xCREDENTIAL", body["credential"])
	}
	out := stdout.String()
	if !strings.Contains(out, "Payment confirmed") || !strings.Contains(out, "0xTXHASH") {
		t.Errorf("expected 'Payment confirmed' + tx hash in stdout, got: %q", out)
	}
}

// TestHandlePaymentRequired_FallsBackToConfigRPCURL asserts that when the
// event omits rpc_url, the configured default is used.
func TestHandlePaymentRequired_FallsBackToConfigRPCURL(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	gotRPC := ""
	restore := withInjectedHelpers(t,
		strings.NewReader("y\n"),
		&bytes.Buffer{},
		func(string) (string, error) { return "p", nil },
		func(string) (any, error) { return "acct", nil },
		func(_ context.Context, _ string, _ any, rpcURL string) (string, string, error) {
			gotRPC = rpcURL
			return "cred", "tx", nil
		},
		nil,
	)
	defer restore()

	ev := sampleEvent()
	ev.RPCURL = "" // force fallback

	if err := HandlePaymentRequired(
		context.Background(),
		false,
		server.URL,
		"tok",
		"sess-1",
		"https://config-default-rpc.example",
		ev,
	); err != nil {
		t.Fatalf("HandlePaymentRequired error: %v", err)
	}
	if gotRPC != "https://config-default-rpc.example" {
		t.Errorf("signCredential rpcURL = %q, want config default", gotRPC)
	}
}

// captureStdout temporarily redirects os.Stdout while fn runs and returns
// what was written. Used because output.JSON writes via fmt.Println.
func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("os.Pipe: %v", err)
	}
	orig := os.Stdout
	os.Stdout = w
	done := make(chan string, 1)
	go func() {
		var buf bytes.Buffer
		_, _ = io.Copy(&buf, r)
		done <- buf.String()
	}()
	fn()
	_ = w.Close()
	os.Stdout = orig
	return <-done
}
