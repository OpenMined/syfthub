// Package heartbeat provides heartbeat management for SyftAPI.
package heartbeat

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

// Manager manages heartbeat signals to SyftHub.
type Manager struct {
	// config
	baseURL  string
	apiKey   string
	spaceURL string
	ttl      time.Duration
	interval time.Duration
	logger   *slog.Logger

	// retry settings
	maxRetries     int
	baseRetryDelay time.Duration

	// internal state
	client    *http.Client
	stopCh    chan struct{}
	stoppedCh chan struct{}
	mu        sync.Mutex
	running   bool
}

// Config holds heartbeat manager configuration.
type Config struct {
	BaseURL            string
	APIKey             string
	SpaceURL           string // URL of this space (e.g., "https://myspace.example.com")
	TTLSeconds         int
	IntervalMultiplier float64
	Logger             *slog.Logger
	MaxRetries         int
	BaseRetryDelay     time.Duration
}

// HeartbeatRequest is the request to send a heartbeat.
type HeartbeatRequest struct {
	URL        string `json:"url"`
	TTLSeconds int    `json:"ttl_seconds"`
}

// HeartbeatResponse is the response from a heartbeat request.
type HeartbeatResponse struct {
	Status     string    `json:"status"`
	ReceivedAt time.Time `json:"received_at"`
	ExpiresAt  time.Time `json:"expires_at"`
	Domain     string    `json:"domain"`
	TTLSeconds int       `json:"ttl_seconds"`
}

// NewManager creates a new heartbeat manager.
func NewManager(cfg *Config) *Manager {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	ttl := time.Duration(cfg.TTLSeconds) * time.Second
	interval := time.Duration(float64(cfg.TTLSeconds)*cfg.IntervalMultiplier) * time.Second

	maxRetries := cfg.MaxRetries
	if maxRetries == 0 {
		maxRetries = 3
	}

	baseRetryDelay := cfg.BaseRetryDelay
	if baseRetryDelay == 0 {
		baseRetryDelay = 5 * time.Second
	}

	return &Manager{
		baseURL:        cfg.BaseURL,
		apiKey:         cfg.APIKey,
		spaceURL:       cfg.SpaceURL,
		ttl:            ttl,
		interval:       interval,
		logger:         logger,
		maxRetries:     maxRetries,
		baseRetryDelay: baseRetryDelay,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		stopCh:    make(chan struct{}),
		stoppedCh: make(chan struct{}),
	}
}

// Start begins sending heartbeat signals.
func (m *Manager) Start(ctx context.Context) error {
	m.mu.Lock()
	if m.running {
		m.mu.Unlock()
		return fmt.Errorf("heartbeat manager already running")
	}
	m.running = true
	m.stopCh = make(chan struct{})
	m.stoppedCh = make(chan struct{})
	m.mu.Unlock()

	defer close(m.stoppedCh)

	m.logger.Info("starting heartbeat manager",
		"ttl", m.ttl,
		"interval", m.interval,
	)

	// Send first heartbeat immediately
	if err := m.sendHeartbeatWithRetry(ctx); err != nil {
		m.logger.Warn("initial heartbeat failed", "error", err)
	}

	ticker := time.NewTicker(m.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			m.logger.Info("heartbeat manager stopped (context cancelled)")
			return ctx.Err()
		case <-m.stopCh:
			m.logger.Info("heartbeat manager stopped")
			return nil
		case <-ticker.C:
			if err := m.sendHeartbeatWithRetry(ctx); err != nil {
				m.logger.Warn("heartbeat failed", "error", err)
			}
		}
	}
}

// Stop stops the heartbeat manager.
func (m *Manager) Stop(ctx context.Context) error {
	m.mu.Lock()
	if !m.running {
		m.mu.Unlock()
		return nil
	}
	m.running = false
	close(m.stopCh)
	m.mu.Unlock()

	// Wait for the manager to stop with timeout
	select {
	case <-m.stoppedCh:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// sendHeartbeatWithRetry sends a heartbeat with retry logic.
func (m *Manager) sendHeartbeatWithRetry(ctx context.Context) error {
	var lastErr error

	for attempt := 0; attempt <= m.maxRetries; attempt++ {
		if attempt > 0 {
			// Exponential backoff
			delay := m.baseRetryDelay * time.Duration(1<<(attempt-1))
			m.logger.Debug("retrying heartbeat",
				"attempt", attempt,
				"delay", delay,
			)

			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(delay):
			}
		}

		resp, err := m.sendHeartbeat(ctx)
		if err == nil {
			// Update interval based on server response
			if resp.TTLSeconds > 0 {
				m.interval = time.Duration(float64(resp.TTLSeconds)*0.8) * time.Second
			}
			m.logger.Debug("heartbeat sent",
				"ttl", resp.TTLSeconds,
				"domain", resp.Domain,
				"expires_at", resp.ExpiresAt,
			)
			return nil
		}

		lastErr = err
	}

	return fmt.Errorf("heartbeat failed after %d attempts: %w", m.maxRetries+1, lastErr)
}

// sendHeartbeat sends a single heartbeat request.
func (m *Manager) sendHeartbeat(ctx context.Context) (*HeartbeatResponse, error) {
	reqBody := HeartbeatRequest{
		URL:        m.spaceURL,
		TTLSeconds: int(m.ttl.Seconds()),
	}

	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", m.baseURL+"/api/v1/users/me/heartbeat", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+m.apiKey)

	resp, err := m.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send heartbeat: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("heartbeat failed with status %d: %s", resp.StatusCode, string(respBody))
	}

	var heartbeatResp HeartbeatResponse
	if err := json.Unmarshal(respBody, &heartbeatResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	return &heartbeatResp, nil
}

// IsRunning returns whether the manager is running.
func (m *Manager) IsRunning() bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.running
}
