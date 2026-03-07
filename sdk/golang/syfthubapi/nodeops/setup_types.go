package nodeops

// Step type constants.
const (
	StepTypePrompt   = "prompt"
	StepTypeSelect   = "select"
	StepTypeOAuth2   = "oauth2"
	StepTypeHTTP     = "http"
	StepTypeTemplate = "template"
	StepTypeExec     = "exec"
)

// Step status constants.
const (
	StepStatusCompleted = "completed"
	StepStatusFailed    = "failed"
)

// Lifecycle strategy constants.
const (
	StrategyRefreshToken = "refresh_token"
)

// SetupSpec is the top-level structure of a setup.yaml file.
type SetupSpec struct {
	Version   string          `yaml:"version" json:"version"`
	Steps     []SetupStep     `yaml:"steps" json:"steps"`
	Lifecycle *SetupLifecycle `yaml:"lifecycle,omitempty" json:"lifecycle,omitempty"`
}

// SetupStep is a single configuration step.
type SetupStep struct {
	// Core fields (all step types)
	ID          string   `yaml:"id" json:"id"`
	Name        string   `yaml:"name" json:"name"`
	Description string   `yaml:"description,omitempty" json:"description,omitempty"`
	Type        string   `yaml:"type" json:"type"` // See StepType* constants
	Required    bool     `yaml:"required" json:"required"`
	DependsOn   []string `yaml:"depends_on,omitempty" json:"depends_on,omitempty"`

	// Output mapping — written to .env after step completes
	// Single value output:
	EnvKey string `yaml:"env_key,omitempty" json:"env_key,omitempty"`
	// Multi-value output (env_key -> template):
	Outputs map[string]string `yaml:"outputs,omitempty" json:"outputs,omitempty"`

	// Type-specific configuration (only the matching one is non-nil)
	Prompt   *PromptConfig   `yaml:"prompt,omitempty" json:"prompt,omitempty"`
	Select   *SelectConfig   `yaml:"select,omitempty" json:"select,omitempty"`
	OAuth2   *OAuth2Config   `yaml:"oauth2,omitempty" json:"oauth2,omitempty"`
	HTTP     *HTTPConfig     `yaml:"http,omitempty" json:"http,omitempty"`
	Template *TemplateConfig `yaml:"template,omitempty" json:"template,omitempty"`
	Exec     *ExecConfig     `yaml:"exec,omitempty" json:"exec,omitempty"`
}

// --- Type-specific configs ---

// PromptConfig configures a text/secret input step.
type PromptConfig struct {
	Message  string          `yaml:"message" json:"message"`
	Secret   bool            `yaml:"secret,omitempty" json:"secret,omitempty"`
	Default  string          `yaml:"default,omitempty" json:"default,omitempty"`
	Validate *ValidateConfig `yaml:"validate,omitempty" json:"validate,omitempty"`
}

// ValidateConfig defines input validation rules.
type ValidateConfig struct {
	Pattern string `yaml:"pattern" json:"pattern"`                     // regex
	Message string `yaml:"message,omitempty" json:"message,omitempty"` // error message on mismatch
}

// SelectConfig configures a selection step.
type SelectConfig struct {
	Message string         `yaml:"message,omitempty" json:"message,omitempty"`
	Options []SelectOption `yaml:"options,omitempty" json:"options,omitempty"` // static options
	Default string         `yaml:"default,omitempty" json:"default,omitempty"`
	// Dynamic options (Phase 2):
	OptionsFrom *OptionsFromConfig `yaml:"options_from,omitempty" json:"options_from,omitempty"`
}

// SelectOption is a single choice in a select step.
type SelectOption struct {
	Value string `yaml:"value" json:"value"`
	Label string `yaml:"label" json:"label"`
}

// OptionsFromConfig fetches select options dynamically from a prior http step.
type OptionsFromConfig struct {
	StepID     string `yaml:"step_id" json:"step_id"`         // id of a prior http step
	Path       string `yaml:"path" json:"path"`               // JSON path to array in response
	ValueField string `yaml:"value_field" json:"value_field"` // field name for option value
	LabelField string `yaml:"label_field" json:"label_field"` // field name for option label
}

// OAuth2Config configures a generic OAuth 2.0 authorization code flow.
type OAuth2Config struct {
	AuthURL         string            `yaml:"auth_url" json:"auth_url"`
	TokenURL        string            `yaml:"token_url" json:"token_url"`
	Scopes          []string          `yaml:"scopes" json:"scopes"`
	ClientID        string            `yaml:"client_id,omitempty" json:"client_id,omitempty"`
	ClientSecret    string            `yaml:"client_secret,omitempty" json:"client_secret,omitempty"`
	ClientIDEnv     string            `yaml:"client_id_env,omitempty" json:"client_id_env,omitempty"`
	ClientSecretEnv string            `yaml:"client_secret_env,omitempty" json:"client_secret_env,omitempty"`
	ExtraParams     map[string]string `yaml:"extra_params,omitempty" json:"extra_params,omitempty"`
	CallbackPort    int               `yaml:"callback_port,omitempty" json:"callback_port,omitempty"` // 0 = random
}

// HTTPConfig configures an HTTP request step.
type HTTPConfig struct {
	Method       string            `yaml:"method" json:"method"` // GET, POST, PUT, DELETE
	URL          string            `yaml:"url" json:"url"`       // supports {{templates}}
	Headers      map[string]string `yaml:"headers,omitempty" json:"headers,omitempty"`
	Query        map[string]string `yaml:"query,omitempty" json:"query,omitempty"`
	JSON         map[string]any    `yaml:"json,omitempty" json:"json,omitempty"`                   // request body (JSON)
	Body         string            `yaml:"body,omitempty" json:"body,omitempty"`                   // raw body (mutually exclusive with json)
	ExpectStatus int               `yaml:"expect_status,omitempty" json:"expect_status,omitempty"` // 0 = accept any 2xx
	TimeoutSecs  int               `yaml:"timeout_secs,omitempty" json:"timeout_secs,omitempty"`   // default: 30
}

// TemplateConfig configures a derived value step.
type TemplateConfig struct {
	Value string `yaml:"value" json:"value"` // template string
}

// ExecConfig configures a shell command execution step.
type ExecConfig struct {
	Command     string            `yaml:"command" json:"command"`                               // shell command to run
	Env         map[string]string `yaml:"env,omitempty" json:"env,omitempty"`                   // extra env vars (supports {{templates}})
	TimeoutSecs int               `yaml:"timeout_secs,omitempty" json:"timeout_secs,omitempty"` // default: 120, max: 600
	Message     string            `yaml:"message,omitempty" json:"message,omitempty"`           // status message shown to user
}

// --- Lifecycle ---

// SetupLifecycle defines automatic re-run triggers.
type SetupLifecycle struct {
	Refresh *LifecycleRefresh `yaml:"refresh,omitempty" json:"refresh,omitempty"`
}

// LifecycleRefresh configures token refresh behavior.
type LifecycleRefresh struct {
	Trigger  string   `yaml:"trigger" json:"trigger"`   // "token_expiry"
	Steps    []string `yaml:"steps" json:"steps"`       // step IDs to re-run
	Strategy string   `yaml:"strategy" json:"strategy"` // "refresh_token", "full_reauth"
}

// --- Setup state ---

// SetupState is persisted in .setup-state.json to track completion.
type SetupState struct {
	Version string               `json:"version"`
	Steps   map[string]StepState `json:"steps"`
}

// StepState tracks the completion status of a single step.
type StepState struct {
	Status      string `json:"status"`                 // "completed", "failed", "skipped", "expired"
	CompletedAt string `json:"completed_at,omitempty"` // RFC3339
	ExpiresAt   string `json:"expires_at,omitempty"`   // RFC3339 (for oauth tokens)
	Error       string `json:"error,omitempty"`        // error message if failed
}

// SetupStatus is the computed status for display.
type SetupStatus struct {
	HasSetup     bool     `json:"has_setup"`   // setup.yaml exists
	IsComplete   bool     `json:"is_complete"` // all required steps done
	TotalSteps   int      `json:"total_steps"`
	CompletedN   int      `json:"completed"`
	PendingSteps []string `json:"pending_steps"` // IDs of incomplete required steps
	ExpiredSteps []string `json:"expired_steps"` // IDs of steps with expired tokens
}
