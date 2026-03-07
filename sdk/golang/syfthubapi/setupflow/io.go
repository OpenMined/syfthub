package setupflow

// SetupIO abstracts user interaction. CLI implements with stdin/stdout,
// desktop implements with Wails UI callbacks.
type SetupIO interface {
	// Prompt asks the user for text input.
	Prompt(message string, opts PromptOpts) (string, error)

	// Select presents a list of options and returns the chosen value.
	Select(message string, options []SelectOption) (string, error)

	// Confirm asks a yes/no question.
	Confirm(message string) (bool, error)

	// OpenBrowser opens a URL in the system browser.
	OpenBrowser(url string) error

	// Status displays a status message (not a prompt — informational).
	Status(message string)

	// Error displays an error message.
	Error(message string)
}

// PromptOpts configures a Prompt call.
type PromptOpts struct {
	Secret      bool   // hide input (for passwords/tokens)
	Default     string // default value shown to user
	Placeholder string // hint text
}

// SelectOption is a choice presented to the user.
type SelectOption struct {
	Value string
	Label string
}
