// Package agenttypes defines shared domain types used by both the hub client
// SDK (syfthub) and the server-side SDK (syfthubapi). Keeping these in a
// separate, dependency-free package prevents circular imports and eliminates
// duplicate struct definitions.
package agenttypes

// Message represents a chat message with a role and content.
type Message struct {
	// Role is the message role: "system", "user", or "assistant".
	Role string `json:"role"`

	// Content is the message content.
	Content string `json:"content"`
}

// AgentConfig contains agent session configuration.
type AgentConfig struct {
	// MaxTokens is the maximum tokens for generation.
	MaxTokens int `json:"max_tokens,omitempty"`

	// Temperature controls randomness.
	Temperature float64 `json:"temperature,omitempty"`

	// SystemPrompt is an optional system prompt override.
	SystemPrompt string `json:"system_prompt,omitempty"`

	// Metadata contains arbitrary configuration data.
	Metadata map[string]any `json:"metadata,omitempty"`
}

// ToolCall represents a tool invocation request from the agent.
type ToolCall struct {
	// ID is a unique identifier for this tool call.
	ID string `json:"tool_call_id"`

	// Name is the tool name.
	Name string `json:"tool_name"`

	// Arguments are the tool arguments.
	Arguments map[string]any `json:"arguments"`

	// RequiresConfirmation indicates if user confirmation is needed.
	RequiresConfirmation bool `json:"requires_confirmation"`

	// Description is a human-readable description of what the tool will do.
	Description string `json:"description,omitempty"`
}

// ToolResult represents the result of a tool execution.
type ToolResult struct {
	// ToolCallID matches the ToolCall.ID.
	ToolCallID string `json:"tool_call_id"`

	// Status is "success" or "error".
	Status string `json:"status"`

	// Result contains the tool output.
	Result any `json:"result,omitempty"`

	// Error contains error details if status is "error".
	Error string `json:"error,omitempty"`

	// DurationMs is the execution time in milliseconds.
	DurationMs int64 `json:"duration_ms,omitempty"`
}
