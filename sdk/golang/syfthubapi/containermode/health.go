package containermode

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

// WaitForHealth polls the container's /health endpoint until it returns 200 OK
// or the timeout expires. Uses exponential backoff from 100ms to 2s.
func WaitForHealth(ctx context.Context, baseURL string, timeout time.Duration, logger *slog.Logger) error {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	client := &http.Client{Timeout: 2 * time.Second}
	url := baseURL + "/health"

	backoff := 100 * time.Millisecond
	maxBackoff := 2 * time.Second
	var lastErr error
	attempt := 0

	for {
		attempt++
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return fmt.Errorf("failed to create health request: %w", err)
		}

		resp, err := client.Do(req)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				logger.Info("container health check passed", "url", url, "attempts", attempt)
				return nil
			}
			lastErr = fmt.Errorf("health check returned status %d", resp.StatusCode)
		} else {
			lastErr = err
		}

		logger.Debug("health check attempt failed", "url", url, "attempt", attempt, "error", lastErr)

		select {
		case <-ctx.Done():
			return fmt.Errorf("health check timed out after %s (%d attempts): %w", timeout, attempt, lastErr)
		case <-time.After(backoff):
		}

		backoff *= 2
		if backoff > maxBackoff {
			backoff = maxBackoff
		}
	}
}
