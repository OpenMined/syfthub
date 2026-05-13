// updater.go wires the internal/updater package into the Wails App.
// Phase 1: notify + hard-gate. Background goroutine, JS bindings,
// state-change event. No binary replacement in this file.
package main

import (
	"context"
	"errors"
	"fmt"
	"net/url"

	"github.com/openmined/syfthub-desktop-gui/internal/updater"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// updateEventName is the Wails event the frontend subscribes to.
const updateEventName = "update:state"

// updaterLogger adapts wails runtime logging to the updater.Logger interface.
type updaterLogger struct{ ctx context.Context }

func (l updaterLogger) Info(msg string)  { runtime.LogInfo(l.ctx, msg) }
func (l updaterLogger) Warn(msg string)  { runtime.LogWarning(l.ctx, msg) }
func (l updaterLogger) Error(msg string) { runtime.LogError(l.ctx, msg) }

// wailsEmitter fans manifest state updates to the frontend.
type wailsEmitter struct{ ctx context.Context }

func (e wailsEmitter) Emit(s updater.State) {
	runtime.EventsEmit(e.ctx, updateEventName, s)
}

// startUpdater initializes the updater Checker and starts its background
// goroutine. Called from app.startup once Wails has handed us a ctx.
func (a *App) startUpdater(ctx context.Context) {
	settingsDir, err := getSettingsDir()
	if err != nil {
		runtime.LogWarning(ctx, fmt.Sprintf("updater: cannot resolve settings dir: %v", err))
		return
	}
	autoCheck := true
	if a.settings != nil {
		autoCheck = a.settings.UpdateAutoCheckEnabled
	}
	c := updater.NewChecker(updater.Options{
		CurrentVersion:   Version,
		CacheDir:         settingsDir,
		Logger:           updaterLogger{ctx: ctx},
		Emitter:          wailsEmitter{ctx: ctx},
		AutoCheckEnabled: autoCheck,
	})
	a.mu.Lock()
	a.updater = c
	a.mu.Unlock()
	c.Start(ctx)

	// Push the initial (possibly cache-seeded) state to the frontend so
	// the banner / modal can render before the first network check.
	runtime.EventsEmit(ctx, updateEventName, c.State())
}

// shutdownUpdater stops the updater goroutine. Called from app.shutdown.
func (a *App) shutdownUpdater() {
	a.mu.RLock()
	c := a.updater
	a.mu.RUnlock()
	if c != nil {
		c.Stop()
	}
}

// GetUpdateState returns the current update state for the frontend.
// Safe to call before startUpdater has run — returns zero State.
func (a *App) GetUpdateState() updater.State {
	a.mu.RLock()
	defer a.mu.RUnlock()
	if a.updater == nil {
		return updater.State{
			Stage:          updater.StageDisabled,
			CurrentVersion: Version,
		}
	}
	return a.updater.State()
}

// CheckForUpdatesNow triggers an immediate update check. Returns
// quickly — the result arrives via the "update:state" event.
func (a *App) CheckForUpdatesNow() {
	a.mu.RLock()
	c := a.updater
	a.mu.RUnlock()
	if c != nil {
		c.CheckNow()
	}
}

// SetAutoCheckEnabled toggles the auto-check preference. Persisted to
// settings.json.
func (a *App) SetAutoCheckEnabled(enabled bool) error {
	a.mu.Lock()
	if a.settings == nil {
		a.settings = DefaultSettings()
	}
	a.settings.UpdateAutoCheckEnabled = enabled
	settings := *a.settings
	c := a.updater
	a.mu.Unlock()

	if err := SaveSettings(&settings); err != nil {
		return fmt.Errorf("save settings: %w", err)
	}
	if c != nil {
		c.SetAutoCheckEnabled(enabled)
	}
	return nil
}

// OpenReleaseNotes opens the supplied URL in the system browser.
// Only HTTPS GitHub URLs are accepted — refuses anything else as a
// defensive measure against bound parameter abuse.
func (a *App) OpenReleaseNotes(rawURL string) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("invalid url: %w", err)
	}
	if u.Scheme != "https" {
		return errors.New("only https URLs are allowed")
	}
	if u.Host != "github.com" {
		return errors.New("only github.com URLs are allowed")
	}
	runtime.BrowserOpenURL(a.ctx, rawURL)
	return nil
}
