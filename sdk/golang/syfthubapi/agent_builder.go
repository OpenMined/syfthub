package syfthubapi

// AgentBuilder builds agent endpoints using the builder pattern.
// Embeds baseEndpointBuilder for shared Name/Description/Version/Enabled logic.
type AgentBuilder struct {
	baseEndpointBuilder
}

// Name sets the endpoint display name.
func (b *AgentBuilder) Name(name string) *AgentBuilder {
	b.setName(name)
	return b
}

// Description sets the endpoint description.
func (b *AgentBuilder) Description(description string) *AgentBuilder {
	b.setDescription(description)
	return b
}

// Version sets the endpoint version.
func (b *AgentBuilder) Version(version string) *AgentBuilder {
	b.setVersion(version)
	return b
}

// Enabled sets whether the endpoint is enabled.
func (b *AgentBuilder) Enabled(enabled bool) *AgentBuilder {
	b.setEnabled(enabled)
	return b
}

// Handler sets the agent handler and registers the endpoint.
func (b *AgentBuilder) Handler(handler AgentHandler) error {
	if err := b.validateForRegistration(); err != nil {
		return err
	}
	if handler == nil {
		return &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "handler",
			Message: "handler is required",
		}
	}

	b.endpoint.invoker = &AgentOneShotInvoker{handler: handler, slug: b.endpoint.Slug}
	return b.api.registerEndpoint(b.endpoint)
}
