package updater

import (
	"context"
	"crypto/rand"
	"math/big"
	"net/http"
	"os"
	"runtime"
	"sync"
	"time"
)

// Defaults for the background check loop.
const (
	StartupGrace = 30 * time.Second
	CheckPeriod  = 24 * time.Hour
	CheckJitter  = 2 * time.Hour
	HTTPTimeout  = 15 * time.Second
)

// Logger is the minimal logging surface the updater needs. It matches
// the runtime.Log* signatures from Wails so the app can pass a thin
// adapter.
type Logger interface {
	Info(string)
	Warn(string)
	Error(string)
}

type nopLogger struct{}

func (nopLogger) Info(string)  {}
func (nopLogger) Warn(string)  {}
func (nopLogger) Error(string) {}

// Emitter publishes state transitions to the frontend.
type Emitter interface {
	Emit(state State)
}

// Options configures a Checker.
type Options struct {
	CurrentVersion   string
	ManifestURL      string // empty → ManifestURL constant (or env override)
	CacheDir         string
	HTTPClient       *http.Client
	Logger           Logger
	Emitter          Emitter
	AutoCheckEnabled bool
	GOOS, GOARCH     string // empty → runtime.GOOS/GOARCH
	Now              func() time.Time
}

// Checker runs the background update-check loop and owns the current
// state. All methods are safe for concurrent use.
type Checker struct {
	opts  Options
	cache *Cache

	mu    sync.RWMutex
	state State

	stopOnce sync.Once
	stopCh   chan struct{}
	doneCh   chan struct{}
	kickCh   chan struct{} // immediate-check requests
}

// NewChecker constructs a Checker but does not start the goroutine.
// Call Start to begin checking.
func NewChecker(opts Options) *Checker {
	if opts.Logger == nil {
		opts.Logger = nopLogger{}
	}
	if opts.HTTPClient == nil {
		opts.HTTPClient = &http.Client{Timeout: HTTPTimeout}
	}
	if opts.GOOS == "" {
		opts.GOOS = runtime.GOOS
	}
	if opts.GOARCH == "" {
		opts.GOARCH = runtime.GOARCH
	}
	if opts.Now == nil {
		opts.Now = time.Now
	}
	if opts.ManifestURL == "" {
		opts.ManifestURL = ManifestURL
		if env := os.Getenv(ManifestEnvOverride); env != "" {
			opts.ManifestURL = env
		}
	}

	c := &Checker{
		opts:   opts,
		cache:  NewCache(opts.CacheDir),
		stopCh: make(chan struct{}),
		doneCh: make(chan struct{}),
		kickCh: make(chan struct{}, 1),
	}

	c.state = State{
		Stage:            initialStage(opts),
		CurrentVersion:   opts.CurrentVersion,
		Platform:         PlatformKey(opts.GOOS, opts.GOARCH),
		AutoCheckEnabled: opts.AutoCheckEnabled,
	}
	// Seed from cache so the UI has a sensible initial picture before the
	// first network check completes.
	if c.state.Stage != StageDisabled {
		if m, fetchedAt, _ := c.cache.Load(); m != nil {
			c.applyManifest(m, fetchedAt, "" /*err*/, opts.Now())
		}
	}
	return c
}

// initialStage decides whether the updater runs at all for this build.
func initialStage(opts Options) Stage {
	if IsDevVersion(opts.CurrentVersion) {
		return StageDisabled
	}
	if v := os.Getenv(SkipEnv); v != "" && v != "0" && v != "false" {
		return StageDisabled
	}
	return StageIdle
}

// State returns a snapshot of the current update state.
func (c *Checker) State() State {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.state
}

// SetAutoCheckEnabled updates the persisted preference on the state.
// Does not start or stop the loop — the loop respects the flag at each
// tick. The new state is published.
func (c *Checker) SetAutoCheckEnabled(enabled bool) {
	c.mu.Lock()
	c.state.AutoCheckEnabled = enabled
	s := c.state
	c.mu.Unlock()
	c.publish(s)
}

// Start launches the background check goroutine. Safe to call once.
// Calling more than once panics — by design, a Checker has one loop.
func (c *Checker) Start(ctx context.Context) {
	go c.run(ctx)
}

// Stop signals the goroutine to exit and waits for it. Safe to call
// multiple times.
func (c *Checker) Stop() {
	c.stopOnce.Do(func() { close(c.stopCh) })
	<-c.doneCh
}

// CheckNow requests an immediate check. Non-blocking — if a check is
// already in progress, the request is dropped.
func (c *Checker) CheckNow() {
	select {
	case c.kickCh <- struct{}{}:
	default:
	}
}

func (c *Checker) run(ctx context.Context) {
	defer close(c.doneCh)

	if c.State().Stage == StageDisabled {
		c.opts.Logger.Info("updater: disabled for this build (dev/pre-release or env override)")
		<-c.stopCh
		return
	}

	// Initial check after startup grace.
	select {
	case <-time.After(StartupGrace):
	case <-c.stopCh:
		return
	case <-ctx.Done():
		return
	case <-c.kickCh:
	}

	c.runOnce(ctx)

	for {
		next := jitter(CheckPeriod, CheckJitter)
		c.opts.Logger.Info("updater: next check in " + next.Round(time.Minute).String())
		timer := time.NewTimer(next)
		select {
		case <-timer.C:
			if c.shouldAutoCheck() {
				c.runOnce(ctx)
			}
		case <-c.kickCh:
			if !timer.Stop() {
				<-timer.C
			}
			c.runOnce(ctx)
		case <-c.stopCh:
			timer.Stop()
			return
		case <-ctx.Done():
			timer.Stop()
			return
		}
	}
}

func (c *Checker) shouldAutoCheck() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.state.AutoCheckEnabled
}

// runOnce performs one manifest fetch + state-update cycle.
func (c *Checker) runOnce(ctx context.Context) {
	prev := c.State()

	checking := prev
	checking.Stage = StageChecking
	c.publish(checking)

	now := c.opts.Now()
	manifest, err := c.fetchWithContext(ctx)
	if err != nil {
		c.applyFetchError(err, now)
		return
	}
	if saveErr := c.cache.Save(manifest, now); saveErr != nil {
		c.opts.Logger.Warn("updater: cache save failed: " + saveErr.Error())
	}
	c.applyManifest(manifest, now, "", now)
}

func (c *Checker) fetchWithContext(ctx context.Context) (*Manifest, error) {
	return fetchManifestCtx(ctx, c.opts.HTTPClient, c.opts.ManifestURL)
}

// applyFetchError computes the offline state from the cache.
func (c *Checker) applyFetchError(err error, now time.Time) {
	cached, fetchedAt, _ := c.cache.Load()
	if cached != nil && IsFresh(fetchedAt, now) {
		// Apply the cached manifest's policy (especially min_supported_version)
		// then mark the state as offline_grace so the UI can show "couldn't
		// reach the update server, using cached info".
		c.applyManifest(cached, fetchedAt, err.Error(), now)
		c.mu.Lock()
		// applyManifest may have produced idle/available/must_update —
		// upgrade idle/available to offline_grace; preserve must_update.
		if c.state.Stage == StageIdle || c.state.Stage == StageAvailable {
			c.state.Stage = StageOfflineGrace
		}
		c.state.LastError = err.Error()
		s := c.state
		c.mu.Unlock()
		c.publish(s)
		return
	}
	c.mu.Lock()
	c.state.Stage = StageOfflineNoGrace
	c.state.LastError = err.Error()
	c.state.LastCheckedAt = now
	s := c.state
	c.mu.Unlock()
	c.publish(s)
}

// applyManifest updates state from a parsed manifest.
// lastErr is empty for live fetches, non-empty when seeded from cache after
// a failed fetch.
func (c *Checker) applyManifest(m *Manifest, fetchedAt time.Time, lastErr string, _ time.Time) {
	c.mu.Lock()
	c.state.LatestVersion = m.Version
	c.state.MinSupportedVersion = m.MinSupportedVersion
	c.state.ReleaseNotesURL = m.ReleaseNotesURL
	c.state.MustUpdateReason = m.MustUpdateReason
	c.state.LastCheckedAt = fetchedAt
	c.state.LastError = lastErr

	asset, supported := m.AssetFor(c.opts.GOOS, c.opts.GOARCH)
	c.state.PlatformSupported = supported
	if supported {
		c.state.DownloadURL = asset.URL
		c.state.DownloadSHA256 = asset.SHA256
		c.state.DownloadSizeBytes = asset.SizeBytes
	} else {
		c.state.DownloadURL = ""
		c.state.DownloadSHA256 = ""
		c.state.DownloadSizeBytes = 0
	}

	switch {
	case CompareSemver(c.state.CurrentVersion, m.MinSupportedVersion) < 0:
		c.state.Stage = StageMustUpdate
	case !supported:
		c.state.Stage = StageUnsupportedPlatform
	case CompareSemver(c.state.CurrentVersion, m.Version) < 0:
		c.state.Stage = StageAvailable
	default:
		c.state.Stage = StageIdle
	}

	s := c.state
	c.mu.Unlock()
	c.publish(s)
}

func (c *Checker) publish(s State) {
	if c.opts.Emitter != nil {
		c.opts.Emitter.Emit(s)
	}
}

// jitter returns base ± rand(0, jit).
func jitter(base, jit time.Duration) time.Duration {
	if jit <= 0 {
		return base
	}
	n, err := rand.Int(rand.Reader, big.NewInt(int64(jit)*2))
	if err != nil {
		return base
	}
	delta := time.Duration(n.Int64()) - jit
	return base + delta
}
