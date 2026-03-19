package main

import (
	"context"
	"fmt"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/pkg/browser"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// WailsSetupIO implements setupflow.SetupIO using Wails events for UI interaction.
// Each interactive method emits a Wails event and blocks on a response channel.
// The frontend shows the appropriate dialog and calls a respond method to unblock.
type WailsSetupIO struct {
	ctx       context.Context // Wails runtime context (for events)
	cancelCtx context.Context // Cancellation context for the setup flow
	promptCh  chan string
	selectCh  chan string
	confirmCh chan bool
}

// NewWailsSetupIO creates a new WailsSetupIO.
func NewWailsSetupIO(wailsCtx context.Context, cancelCtx context.Context) *WailsSetupIO {
	return &WailsSetupIO{
		ctx:       wailsCtx,
		cancelCtx: cancelCtx,
		promptCh:  make(chan string, 1),
		selectCh:  make(chan string, 1),
		confirmCh: make(chan bool, 1),
	}
}

// PromptEvent is the payload emitted to the frontend for prompt requests.
type PromptEvent struct {
	Message     string `json:"message"`
	Secret      bool   `json:"secret"`
	Default     string `json:"default,omitempty"`
	Placeholder string `json:"placeholder,omitempty"`
}

// SelectEvent is the payload emitted to the frontend for select requests.
type SelectEvent struct {
	Message string             `json:"message"`
	Options []SelectOptionInfo `json:"options"`
}

// SelectOptionInfo is a choice presented in a select event.
type SelectOptionInfo struct {
	Value string `json:"value"`
	Label string `json:"label"`
}

// ConfirmEvent is the payload emitted to the frontend for confirm requests.
type ConfirmEvent struct {
	Message string `json:"message"`
}

func (io *WailsSetupIO) Prompt(message string, opts setupflow.PromptOpts) (string, error) {
	runtime.EventsEmit(io.ctx, "setupflow:prompt", PromptEvent{
		Message:     message,
		Secret:      opts.Secret,
		Default:     opts.Default,
		Placeholder: opts.Placeholder,
	})

	select {
	case value := <-io.promptCh:
		return value, nil
	case <-io.cancelCtx.Done():
		return "", fmt.Errorf("setup cancelled")
	}
}

func (io *WailsSetupIO) Select(message string, options []setupflow.SelectOption) (string, error) {
	opts := make([]SelectOptionInfo, len(options))
	for i, o := range options {
		opts[i] = SelectOptionInfo{Value: o.Value, Label: o.Label}
	}

	runtime.EventsEmit(io.ctx, "setupflow:select", SelectEvent{
		Message: message,
		Options: opts,
	})

	select {
	case value := <-io.selectCh:
		return value, nil
	case <-io.cancelCtx.Done():
		return "", fmt.Errorf("setup cancelled")
	}
}

func (io *WailsSetupIO) Confirm(message string) (bool, error) {
	runtime.EventsEmit(io.ctx, "setupflow:confirm", ConfirmEvent{
		Message: message,
	})

	select {
	case confirmed := <-io.confirmCh:
		return confirmed, nil
	case <-io.cancelCtx.Done():
		return false, fmt.Errorf("setup cancelled")
	}
}

func (io *WailsSetupIO) OpenBrowser(url string) error {
	return browser.OpenURL(url)
}

func (io *WailsSetupIO) Status(message string) {
	runtime.EventsEmit(io.ctx, "setupflow:status", message)
}

func (io *WailsSetupIO) Error(message string) {
	runtime.EventsEmit(io.ctx, "setupflow:error", message)
}
