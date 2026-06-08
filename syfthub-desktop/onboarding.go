// onboarding.go implements the passwordless email sign-in flow that replaces
// the legacy "paste an API key" setup. The user enters only their email; the
// hub emails a one-time code; verifying it yields a JWT session (provisioning a
// passwordless account on first use, like OAuth). From that session we mint a
// Personal Access Token (PAT) and persist it via the existing SaveSettingsData
// path — so the rest of the app sees exactly the same configured state it would
// have seen from a pasted PAT.
package main

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	syfthub "github.com/openmined/syfthub/sdk/golang/syfthub"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// onboardingTimeout bounds every network call made during onboarding.
const onboardingTimeout = 15 * time.Second

// onboardingState holds the transient context of an in-progress email sign-in.
// The *syfthub.Client carries the JWT session once the OTP is verified
// (tokenless until then). It is guarded by its own mutex so onboarding never
// contends with the App's primary a.mu.
type onboardingState struct {
	mu            sync.Mutex
	client        *syfthub.Client // tokenless client awaiting OTP verification; nil when idle
	email         string          // email the code was sent to (for verify/resend)
	hubURL        string          // hub URL to persist on finalize
	endpointsPath string          // endpoints path to persist on finalize
}

// onboardingCtx returns a context bounded by the onboarding timeout, parented
// on the Wails runtime context when available.
func (a *App) onboardingCtx() (context.Context, context.CancelFunc) {
	parent := a.ctx
	if parent == nil {
		parent = context.Background()
	}
	return context.WithTimeout(parent, onboardingTimeout)
}

// restoreOnboardingClient re-stashes the client under the lock so the user can
// retry after a failed verify or finalize step.
func (a *App) restoreOnboardingClient(client *syfthub.Client) {
	a.onboarding.mu.Lock()
	a.onboarding.client = client
	a.onboarding.mu.Unlock()
}

// clearOnboardingState resets the transient onboarding fields to idle under the
// lock. Called once the flow has terminally completed.
func (a *App) clearOnboardingState() {
	a.onboarding.mu.Lock()
	a.onboarding.client = nil
	a.onboarding.email = ""
	a.onboarding.hubURL = ""
	a.onboarding.endpointsPath = ""
	a.onboarding.mu.Unlock()
}

// StartEmailSignIn begins the passwordless email sign-in: it asks the hub to
// email a one-time code to the given address and stashes the tokenless client
// for the upcoming verification step. The frontend then collects the code and
// calls VerifyEmailSignIn.
//
// The account is provisioned lazily by the hub on first successful
// verification, so this neither requires nor reveals whether an account already
// exists. Returns the server error verbatim (e.g. 503 when email sign-in is
// unavailable, 429 when rate-limited) for the frontend to surface.
func (a *App) StartEmailSignIn(hubURL, email, endpointsPath string) error {
	client, err := syfthub.NewClient(syfthub.WithBaseURL(hubURL))
	if err != nil {
		return fmt.Errorf("failed to create client: %w", err)
	}

	ctx, cancel := a.onboardingCtx()
	defer cancel()

	if err := client.Auth.RequestEmailOTP(ctx, email); err != nil {
		return err
	}

	a.onboarding.mu.Lock()
	a.onboarding.client = client
	a.onboarding.email = email
	a.onboarding.hubURL = hubURL
	a.onboarding.endpointsPath = endpointsPath
	a.onboarding.mu.Unlock()

	runtime.LogInfo(a.ctx, fmt.Sprintf("Sent email sign-in code to %s — awaiting verification", email))
	return nil
}

// VerifyEmailSignIn verifies the one-time code for the in-progress email
// sign-in using the stashed client + email, which sets the JWT on the client,
// then finalizes onboarding (mint PAT + persist).
func (a *App) VerifyEmailSignIn(code string) error {
	// Atomically claim the flow by nulling the stashed client under the lock.
	// A concurrent VerifyEmailSignIn then sees nil and bails, so the PAT can
	// never be minted twice. The client is restored below if verification fails
	// so the user can retry with a corrected code.
	a.onboarding.mu.Lock()
	client := a.onboarding.client
	email := a.onboarding.email
	hubURL := a.onboarding.hubURL
	endpointsPath := a.onboarding.endpointsPath
	a.onboarding.client = nil
	a.onboarding.mu.Unlock()

	if client == nil {
		return errors.New("no sign-in in progress; please request a code again")
	}

	ctx, cancel := a.onboardingCtx()
	defer cancel()

	if _, err := client.Auth.VerifyEmailOTP(ctx, email, code); err != nil {
		// Restore the stash so the user can re-enter the code.
		a.restoreOnboardingClient(client)
		return err
	}

	if err := a.finalizeOnboarding(client, hubURL, endpointsPath); err != nil {
		// Code verified but PAT mint/persist failed. Restore the stash so the
		// user can retry finalize (re-verifying is unnecessary but harmless).
		a.restoreOnboardingClient(client)
		return err
	}

	runtime.LogInfo(a.ctx, fmt.Sprintf("Verified email sign-in and onboarded %s", email))
	return nil
}

// ResendEmailSignIn re-sends the one-time code for the in-progress sign-in to
// the stashed email. Rate-limited server-side.
func (a *App) ResendEmailSignIn() error {
	a.onboarding.mu.Lock()
	client := a.onboarding.client
	email := a.onboarding.email
	a.onboarding.mu.Unlock()

	if client == nil {
		return errors.New("no sign-in in progress; please request a code again")
	}

	ctx, cancel := a.onboardingCtx()
	defer cancel()

	return client.Auth.RequestEmailOTP(ctx, email)
}

// finalizeOnboarding mints a full-scope PAT over the JWT session carried by
// client, then persists it exactly like the legacy pasted-key path via the
// existing a.SaveSettingsData (which writes api_token, flips IsConfigured,
// inits the SDK client, and emits "app:config-ready"). Onboarding state is
// cleared on success.
//
// The onboarding context below bounds only the PAT-mint call. SaveSettingsData
// (called further down with no ctx) performs its own network I/O — initSyftClient.Me
// under its own internal timeout — and so runs outside the onboarding context.
func (a *App) finalizeOnboarding(client *syfthub.Client, hubURL, endpointsPath string) error {
	ctx, cancel := a.onboardingCtx()
	defer cancel()

	resp, err := client.APITokens().Create(ctx, &syfthub.CreateAPITokenRequest{
		Name:   "SyftHub Desktop",
		Scopes: []syfthub.APITokenScope{syfthub.APITokenScopeFull},
	})
	if err != nil {
		return fmt.Errorf("failed to create API token: %w", err)
	}
	if resp.Token == "" {
		return errors.New("server returned an empty API token")
	}

	// Persist via the existing path (sets IsConfigured, inits client, emits event).
	if err := a.SaveSettingsData(hubURL, resp.Token, endpointsPath); err != nil {
		return err
	}

	// Clear transient onboarding state — flow is complete.
	a.clearOnboardingState()

	return nil
}
