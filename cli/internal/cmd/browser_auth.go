package cmd

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net"
	"net/http"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

// generateState creates a cryptographically random 16-byte state nonce encoded as hex.
// Used to prevent CSRF on the local callback server.
func generateState() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("failed to generate random state: %w", err)
	}
	return hex.EncodeToString(b), nil
}

// openBrowser opens the default system browser to the given URL.
// Errors are non-fatal — callers should print the URL as a fallback.
func openBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "windows":
		// "start" is a cmd.exe built-in, so we need cmd /c
		cmd = exec.Command("cmd", "/c", "start", "", url)
	default: // linux and others
		cmd = exec.Command("xdg-open", url)
	}
	return cmd.Start()
}

// browserAuthResult carries the result of the callback from the browser.
type browserAuthResult struct {
	token string
	err   error
}

// cliSuccessHTML is served to the browser after the CLI receives the token.
// window.close() may be blocked by the browser; the fallback text handles that case.
const cliSuccessHTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SyftHub CLI — Setup Complete</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f0f10;
      color: #e5e5e7;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1rem;
    }
    .card {
      background: #1a1a1e;
      border: 1px solid #2e2e32;
      border-radius: 16px;
      padding: 2.5rem 3rem;
      text-align: center;
      max-width: 420px;
      width: 100%;
    }
    .icon {
      width: 56px; height: 56px;
      background: #16a34a22;
      border: 1.5px solid #16a34a55;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 1.25rem;
      font-size: 1.5rem;
    }
    h1 { font-size: 1.25rem; font-weight: 600; margin-bottom: .5rem; }
    p  { color: #a1a1aa; font-size: .9rem; line-height: 1.5; }
    .hint { margin-top: 1.5rem; font-size: .8rem; color: #52525b; display: none; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✓</div>
    <h1>All set!</h1>
    <p>Your API token has been sent to the CLI.<br>Return to your terminal to continue.</p>
    <p class="hint" id="hint">This tab can be safely closed.</p>
  </div>
  <script>
    setTimeout(function() {
      window.close();
      document.getElementById('hint').style.display = 'block';
    }, 1200);
  </script>
</body>
</html>`

// startBrowserAuthFlow starts a one-shot local HTTP callback server, opens the
// browser to the CLI setup page, and waits for the user to create an API token.
//
// The onReady callback is called once the server is listening and the URL is
// known — use it to print the URL and start any progress output.
//
// Returns the API token string on success, or an error if the flow times out,
// is cancelled, or receives an invalid callback.
func startBrowserAuthFlow(ctx context.Context, hubURL string, onReady func(setupURL string)) (string, error) {
	state, err := generateState()
	if err != nil {
		return "", err
	}

	// Bind to 127.0.0.1:0 — the OS assigns a free port.
	// Binding before opening the browser avoids a race where the browser
	// loads the page before the server is ready.
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return "", fmt.Errorf("failed to start callback server: %w", err)
	}
	port := listener.Addr().(*net.TCPAddr).Port

	resultCh := make(chan browserAuthResult, 1)

	mux := http.NewServeMux()
	server := &http.Server{
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	mux.HandleFunc("/cli/done", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		receivedState := r.URL.Query().Get("state")
		token := r.URL.Query().Get("token")

		if receivedState != state {
			http.Error(w, "invalid state", http.StatusBadRequest)
			sendResult(resultCh, browserAuthResult{err: fmt.Errorf("state mismatch — possible CSRF attempt")})
			return
		}

		if token == "" {
			http.Error(w, "missing token", http.StatusBadRequest)
			sendResult(resultCh, browserAuthResult{err: fmt.Errorf("browser sent empty token")})
			return
		}

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, cliSuccessHTML)

		sendResult(resultCh, browserAuthResult{token: token})

		// Shut down the server after the response is flushed.
		go func() {
			time.Sleep(300 * time.Millisecond)
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			server.Shutdown(shutdownCtx) //nolint:errcheck
		}()
	})

	go func() { server.Serve(listener) }() //nolint:errcheck

	setupURL := fmt.Sprintf("%s/cli-setup?port=%d&state=%s",
		strings.TrimRight(hubURL, "/"), port, state)

	// Notify the caller — they can print the URL and start a spinner/timer.
	if onReady != nil {
		onReady(setupURL)
	}

	// Try to open the browser (best-effort; errors are ignored here because
	// onReady already printed the URL as a manual fallback).
	_ = openBrowser(setupURL)

	// Wait for the token, a timeout, or context cancellation.
	const authTimeout = 5 * time.Minute
	timer := time.NewTimer(authTimeout)
	defer timer.Stop()
	select {
	case result := <-resultCh:
		return result.token, result.err
	case <-timer.C:
		server.Close() //nolint:errcheck
		return "", fmt.Errorf("timed out after %v waiting for browser authentication", authTimeout)
	case <-ctx.Done():
		server.Close() //nolint:errcheck
		return "", ctx.Err()
	}
}

// sendResult sends a result to the channel without blocking (the channel is
// buffered-1, so a duplicate callback from a malicious request just drops).
func sendResult(ch chan<- browserAuthResult, r browserAuthResult) {
	select {
	case ch <- r:
	default:
	}
}
