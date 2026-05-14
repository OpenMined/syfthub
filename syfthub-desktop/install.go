// install.go wires the updater.Installer (Phase 3) into Wails App
// bindings. It owns the drain sequence, install state events, and
// in-place binary swap on Linux + Windows. macOS routes through the
// Phase 2 assisted-download path.
package main

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/openmined/syfthub-desktop-gui/internal/updater"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// installEventName is the Wails event channel for install progress.
const installEventName = "update:install"

type installEmitter struct{ ctx context.Context }

func (e installEmitter) EmitInstall(s updater.InstallState) {
	runtime.EventsEmit(e.ctx, installEventName, s)
}

// runtimeQuitter calls runtime.Quit(ctx) so the Wails OnShutdown hook
// runs (which gives the App layer a chance to finish any housekeeping).
type runtimeQuitter struct{ ctx context.Context }

func (q runtimeQuitter) Quit() { runtime.Quit(q.ctx) }

// initInstaller is called from app.startup. It also wires the boot guard
// for rollback detection (handled in main.go before Wails starts) and
// schedules the clean-boot marker that resets the rollback counter.
func (a *App) initInstaller(ctx context.Context) {
	dir, err := getSettingsDir()
	if err != nil {
		runtime.LogWarning(ctx, fmt.Sprintf("installer: cannot resolve settings dir: %v", err))
		return
	}
	inst := updater.NewInstaller(dir, installEmitter{ctx: ctx}, updaterLogger{ctx: ctx})
	a.mu.Lock()
	a.installer = inst
	a.mu.Unlock()
}

// scheduleCleanBootMarker writes the "clean boot" marker to launch
// state after MinCleanBootSeconds of uninterrupted runtime. Called
// once at startup.
func (a *App) scheduleCleanBootMarker(ctx context.Context) {
	go func() {
		select {
		case <-time.After(time.Duration(updater.MinCleanBootSeconds) * time.Second):
		case <-ctx.Done():
			return
		}
		dir, err := getSettingsDir()
		if err != nil {
			return
		}
		bg := updater.NewBootGuard(dir, "")
		bg.MarkCleanBoot()
		runtime.LogDebug(ctx, "updater: clean-boot marker recorded")
	}()
}

// GetInstallState returns an idle InstallState. Exists so Wails includes
// updater.InstallState in the generated TypeScript bindings — the live
// state is delivered to the frontend via the "update:install" event.
func (a *App) GetInstallState() updater.InstallState {
	return updater.InstallState{Stage: updater.InstallIdle}
}

// InstallUpdate performs the in-place swap and relaunch.
// Returns ErrUnsupportedPlatform on macOS until Phase 4.
func (a *App) InstallUpdate() error {
	a.mu.RLock()
	inst := a.installer
	dl := a.downloader
	c := a.updater
	a.mu.RUnlock()

	if inst == nil || dl == nil || c == nil {
		return errors.New("updater not initialized")
	}
	s := c.State()
	if !s.PlatformSupported {
		return errors.New("no install available for this platform")
	}
	if s.LatestVersion == "" || s.DownloadURL == "" || s.DownloadSHA256 == "" {
		return errors.New("no update available")
	}

	localPath, ok := dl.LookupExisting(s.LatestVersion, s.DownloadURL, s.DownloadSHA256)
	if !ok {
		return errors.New("update artifact not downloaded — call DownloadUpdate first")
	}

	// Run install on a goroutine so the binding returns to the JS side
	// before the swap-and-quit dance.
	go func() {
		ctx := context.Background()
		if err := inst.Install(ctx, s.LatestVersion, localPath, s.DownloadSHA256, a.drainForUpdate, runtimeQuitter{ctx: a.ctx}); err != nil {
			runtime.LogError(a.ctx, fmt.Sprintf("install failed: %v", err))
		}
	}()
	return nil
}

// drainForUpdate is the DrainFunc handed to the installer. It must
// stop the node daemon, end agent sessions, close NATS, flush state.
//
// We deliberately do NOT call a.shutdown here — the runtime.Quit invoked
// by the installer after the swap will fire OnShutdown, which calls
// a.shutdown. We just need to put the core app into a state where the
// final shutdown won't have anything outstanding to do.
func (a *App) drainForUpdate(ctx context.Context) error {
	runtime.LogInfo(a.ctx, "updater: draining for install")

	// 1. Cancel any in-flight chat stream.
	a.chatMu.Lock()
	if a.chatCancel != nil {
		a.chatCancel()
		a.chatCancel = nil
	}
	a.chatMu.Unlock()

	// 2. End the active agent session, if any.
	if err := a.StopAgentSession(); err != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("drain: stop agent session: %v", err))
	}

	// 3. Stop the core app (node daemon, NATS, endpoint subprocesses).
	a.mu.RLock()
	running := a.state == StateRunning || a.state == StateStarting
	a.mu.RUnlock()
	if running {
		if err := a.Stop(); err != nil {
			return fmt.Errorf("stop core app: %w", err)
		}
	}

	// 4. Persist settings (they might already be on disk but a final
	//    flush before the swap is cheap insurance).
	a.mu.RLock()
	settings := a.settings
	a.mu.RUnlock()
	if settings != nil {
		if err := SaveSettings(settings); err != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("drain: save settings: %v", err))
		}
	}
	return nil
}
