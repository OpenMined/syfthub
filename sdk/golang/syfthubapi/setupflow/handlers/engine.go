package handlers

import (
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// NewDefaultEngine creates a setupflow engine with all built-in handlers registered.
// This is the standard engine used by the CLI and desktop app.
func NewDefaultEngine() *setupflow.Engine {
	return setupflow.NewEngine(
		setupflow.WithHandler(nodeops.StepTypePrompt, &PromptHandler{}),
		setupflow.WithHandler(nodeops.StepTypeSelect, &SelectHandler{}),
		setupflow.WithHandler(nodeops.StepTypeOAuth2, &OAuth2Handler{}),
		setupflow.WithHandler(nodeops.StepTypeHTTP, NewHTTPHandler()),
		setupflow.WithHandler(nodeops.StepTypeTemplate, &TemplateHandler{}),
		setupflow.WithHandler(nodeops.StepTypeExec, &ExecHandler{}),
	)
}
