package filemode

import (
	"context"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
)

// ReloadCallback is called when endpoints need to be reloaded.
type ReloadCallback func(affectedDirs []string)

// Watcher watches the endpoints directory for changes.
type Watcher struct {
	basePath       string
	debounce       time.Duration
	logger         *slog.Logger
	callback       ReloadCallback
	ignorePatterns []string

	watcher   *fsnotify.Watcher
	mu        sync.Mutex
	running   bool
	stopCh    chan struct{}
	stoppedCh chan struct{}

	// Debouncing state
	pending    map[string]time.Time
	pendingMu  sync.Mutex
	debounceCh chan struct{}
}

// WatcherConfig holds watcher configuration.
type WatcherConfig struct {
	BasePath       string
	DebounceDelay  time.Duration
	Logger         *slog.Logger
	Callback       ReloadCallback
	IgnorePatterns []string
}

// NewWatcher creates a new file system watcher.
func NewWatcher(cfg *WatcherConfig) (*Watcher, error) {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	debounce := cfg.DebounceDelay
	if debounce == 0 {
		debounce = time.Second
	}

	ignorePatterns := cfg.IgnorePatterns
	if len(ignorePatterns) == 0 {
		ignorePatterns = []string{
			"__pycache__",
			".git",
			".venv",
			"venv",
			// ".env" removed - we want to reload when env vars change
			"node_modules",
			".mypy_cache",
			".pytest_cache",
			"*.pyc",
			"*.pyo",
			".DS_Store",
			".policy_store.db", // SQLite policy store
		}
	}

	return &Watcher{
		basePath:       cfg.BasePath,
		debounce:       debounce,
		logger:         logger,
		callback:       cfg.Callback,
		ignorePatterns: ignorePatterns,
		pending:        make(map[string]time.Time),
		stopCh:         make(chan struct{}),
		stoppedCh:      make(chan struct{}),
		debounceCh:     make(chan struct{}, 1),
	}, nil
}

// Start begins watching for file changes.
func (w *Watcher) Start(ctx context.Context) error {
	w.mu.Lock()
	if w.running {
		w.mu.Unlock()
		return nil
	}
	w.running = true
	w.stopCh = make(chan struct{})
	w.stoppedCh = make(chan struct{})
	w.mu.Unlock()

	defer close(w.stoppedCh)

	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	w.watcher = watcher
	defer watcher.Close()

	// Add all directories recursively
	if err := w.addWatchDirs(); err != nil {
		return err
	}

	w.logger.Info("file watcher started",
		"path", w.basePath,
		"debounce", w.debounce,
	)

	// Start debounce processor
	go w.processDebounced(ctx)

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-w.stopCh:
			return nil
		case event, ok := <-watcher.Events:
			if !ok {
				return nil
			}
			w.handleEvent(event)
		case err, ok := <-watcher.Errors:
			if !ok {
				return nil
			}
			w.logger.Error("watcher error", "error", err)
		}
	}
}

// Stop stops the watcher.
func (w *Watcher) Stop(ctx context.Context) error {
	w.mu.Lock()
	if !w.running {
		w.mu.Unlock()
		return nil
	}
	w.running = false
	close(w.stopCh)
	w.mu.Unlock()

	select {
	case <-w.stoppedCh:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// addWatchDirs adds all directories under basePath to the watcher.
func (w *Watcher) addWatchDirs() error {
	return filepath.Walk(w.basePath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if !info.IsDir() {
			return nil
		}

		// Check if should be ignored
		if w.shouldIgnore(path) {
			return filepath.SkipDir
		}

		if err := w.watcher.Add(path); err != nil {
			w.logger.Warn("failed to watch directory",
				"path", path,
				"error", err,
			)
			return nil
		}

		w.logger.Debug("watching directory", "path", path)
		return nil
	})
}

// handleEvent processes a file system event.
func (w *Watcher) handleEvent(event fsnotify.Event) {
	// Ignore if path should be ignored
	if w.shouldIgnore(event.Name) {
		return
	}

	w.logger.Debug("file event",
		"path", event.Name,
		"op", event.Op.String(),
	)

	// Get the endpoint directory (first level under basePath)
	endpointDir := w.getEndpointDir(event.Name)
	if endpointDir == "" {
		return
	}

	// Add to pending with debounce
	w.pendingMu.Lock()
	w.pending[endpointDir] = time.Now()
	w.pendingMu.Unlock()

	// Signal debounce processor
	select {
	case w.debounceCh <- struct{}{}:
	default:
	}

	// Handle new directories
	if event.Op&fsnotify.Create != 0 {
		info, err := os.Stat(event.Name)
		if err == nil && info.IsDir() && !w.shouldIgnore(event.Name) {
			w.watcher.Add(event.Name)
		}
	}
}

// processDebounced processes pending changes after debounce delay.
func (w *Watcher) processDebounced(ctx context.Context) {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-w.stopCh:
			return
		case <-ticker.C:
			w.checkPending()
		case <-w.debounceCh:
			// Reset ticker on new events
		}
	}
}

// checkPending checks for changes that have passed the debounce period.
func (w *Watcher) checkPending() {
	w.pendingMu.Lock()
	defer w.pendingMu.Unlock()

	now := time.Now()
	var ready []string

	for dir, t := range w.pending {
		if now.Sub(t) >= w.debounce {
			ready = append(ready, dir)
			delete(w.pending, dir)
		}
	}

	if len(ready) > 0 && w.callback != nil {
		w.logger.Info("reloading endpoints",
			"dirs", ready,
		)
		go w.callback(ready)
	}
}

// shouldIgnore returns true if the path should be ignored.
func (w *Watcher) shouldIgnore(path string) bool {
	name := filepath.Base(path)

	for _, pattern := range w.ignorePatterns {
		if strings.HasPrefix(pattern, "*") {
			// Suffix match
			suffix := pattern[1:]
			if strings.HasSuffix(name, suffix) {
				return true
			}
		} else {
			// Exact match
			if name == pattern {
				return true
			}
		}
	}

	// Also ignore hidden files/dirs (except .env which we want to watch)
	if strings.HasPrefix(name, ".") && name != ".env" {
		return true
	}

	return false
}

// getEndpointDir returns the endpoint directory for a given path.
func (w *Watcher) getEndpointDir(path string) string {
	// Get path relative to basePath
	rel, err := filepath.Rel(w.basePath, path)
	if err != nil {
		return ""
	}

	// Get the first component (endpoint directory)
	parts := strings.Split(rel, string(filepath.Separator))
	if len(parts) == 0 {
		return ""
	}

	endpointDir := parts[0]
	if endpointDir == "." || endpointDir == ".." {
		return ""
	}

	return filepath.Join(w.basePath, endpointDir)
}
