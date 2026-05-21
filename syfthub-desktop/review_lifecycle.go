package main

// Lifecycle plumbing for the manual-review resolution channel.
//
// The two pieces (publisher + inbox listener) both ride the shared NATS
// connection that core.Setup() established. We wire them once at Setup
// completion and tear them down on Stop. The frontend never sees this
// directly — it only sees the Wails event "manual-review:resolved" emitted
// from the listener's notify callback.

import (
	"context"
	"fmt"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/openmined/syfthub-desktop-gui/internal/app"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

// setupManualReviewDelivery wires the host-side publisher and the caller-side
// inbox listener once the NATS transport is up. It does both jobs because
// the desktop is a symmetric peer — every desktop install is simultaneously
// "the host that owns endpoints" and "the caller in someone else's chat",
// so we need both directions on the same NATS connection.
//
// Best-effort: a JetStream-less NATS server, a missing username, or a
// publisher/listener construction failure each surface as a single log
// line and a nil field — the rest of the app continues without
// manual-review delivery.
func (a *App) setupManualReviewDelivery(ctx context.Context, core *app.App) {
	natsConn := core.NATSConn()
	identityKey := core.HostPrivateKey()
	if natsConn == nil || identityKey == nil {
		runtime.LogDebug(a.ctx, "manual-review delivery disabled — running in HTTP mode")
		return
	}

	// Provision the durable JetStream stream first so both publisher and
	// listener can rely on its existence. provisionMRResolutionsStream is
	// idempotent — multiple desktops racing is safe.
	if err := provisionMRResolutionsStream(natsConn.Conn(), a.core.Logger()); err != nil {
		runtime.LogWarning(a.ctx, "manual-review stream provisioning failed: "+err.Error())
		// Continue: pub/sub still works on a JetStream-less server for the
		// peer-channel best-effort path; the durable inbox just won't be
		// available until the operator enables JetStream.
	}

	// Build the publisher. It is host-perspective — the desktop publishes
	// resolutions for held requests the owner approved.
	pub, err := NewReviewPublisher(natsConn.Conn(), identityKey, a.core.Logger())
	if err != nil {
		runtime.LogWarning(a.ctx, "manual-review publisher disabled: "+err.Error())
	} else {
		a.mu.Lock()
		a.reviewPublisher = pub
		a.mu.Unlock()
		runtime.LogInfo(a.ctx, "manual-review publisher wired")
	}

	// Build the listener. It is caller-perspective — the desktop subscribes
	// to its own inbox so resolutions for requests THIS user submitted
	// land in sent_reviews.
	identity := a.currentIdentity()
	deviceID := a.deviceIDLocked()
	if identity == "" || deviceID == "" {
		runtime.LogDebug(a.ctx, "manual-review listener deferred — identity or device id not yet available")
		return
	}
	listener, err := NewReviewInboxListener(
		natsConn.Conn(),
		identityKey,
		identity,
		deviceID,
		func(env manualreview.ResolvedEnvelope, payload manualreview.ResolvedPayload, seq uint64) (bool, error) {
			return a.ApplyHostResolution(identity, env, payload, seq)
		},
		func(env manualreview.ResolvedEnvelope, payload manualreview.ResolvedPayload) {
			runtime.EventsEmit(a.ctx, "manual-review:resolved", map[string]any{
				"reviewId":      env.ReviewID,
				"status":        payload.Status,
				"endpointSlug":  env.EndpointSlug,
				"endpointOwner": env.EndpointOwner,
			})
		},
		a.core.Logger(),
	)
	if err != nil {
		runtime.LogWarning(a.ctx, "manual-review listener disabled: "+err.Error())
		return
	}
	if err := listener.Start(ctx); err != nil {
		runtime.LogWarning(a.ctx, "manual-review listener start failed: "+err.Error())
		return
	}
	a.mu.Lock()
	a.reviewInboxListener = listener
	a.mu.Unlock()
	runtime.LogInfo(a.ctx,
		fmt.Sprintf("manual-review listener wired (identity=%s device=%s)", identity, deviceID))
}

// teardownManualReviewDelivery stops the listener (the publisher has no
// resources to release beyond the shared NATS conn the core app owns).
// Called on Stop and on logout/identity change.
func (a *App) teardownManualReviewDelivery() {
	a.mu.Lock()
	listener := a.reviewInboxListener
	a.reviewInboxListener = nil
	a.reviewPublisher = nil
	a.mu.Unlock()
	if listener != nil {
		listener.Stop()
		runtime.LogInfo(a.ctx, "manual-review listener stopped")
	}
}

// deviceIDLocked returns the persistent device id, loading it if needed.
// The settings file is the source of truth; LoadSettings mints one on first
// run. Caller MUST hold a.mu OR not need consistency with other settings
// fields — this is a single-field read.
func (a *App) deviceIDLocked() string {
	a.mu.RLock()
	defer a.mu.RUnlock()
	if a.settings == nil {
		return ""
	}
	return a.settings.DeviceID
}
