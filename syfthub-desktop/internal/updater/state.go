package updater

import "time"

// Stage is the high-level update state surfaced to the UI.
type Stage string

const (
	StageDisabled            Stage = "disabled"            // Dev build or SkipEnv set
	StageIdle                Stage = "idle"                // Up to date, above min_supported
	StageAvailable           Stage = "available"           // New version available, above min_supported
	StageMustUpdate          Stage = "must_update"         // Below min_supported, hard-gate
	StageOfflineGrace        Stage = "offline_grace"       // Manifest unreachable, cached manifest fresh
	StageOfflineNoGrace      Stage = "offline_no_grace"    // Manifest unreachable, cache expired or missing
	StageUnsupportedPlatform Stage = "unsupported_platform"
	StageChecking            Stage = "checking"            // Transient — between fire and result
)

// State is what the frontend reads via GetUpdateState() and receives in
// "update:state" events. Field names use snake_case for JS friendliness.
//
// DownloadURL and DownloadSHA256 are kept out of JSON — the React side
// never needs them (downloads are kicked off via DownloadUpdate() which
// reads these server-side), and there's no value in surfacing them to
// the renderer process.
type State struct {
	Stage              Stage     `json:"stage"`
	CurrentVersion     string    `json:"current_version"`
	LatestVersion      string    `json:"latest_version,omitempty"`
	MinSupportedVersion string   `json:"min_supported_version,omitempty"`
	ReleaseNotesURL    string    `json:"release_notes_url,omitempty"`
	MustUpdateReason   string    `json:"must_update_reason,omitempty"`
	Platform           string    `json:"platform"` // goos/goarch
	PlatformSupported  bool      `json:"platform_supported"`
	DownloadURL        string    `json:"-"`
	DownloadSHA256     string    `json:"-"`
	DownloadSizeBytes  int64     `json:"download_size_bytes,omitempty"`
	LastCheckedAt      time.Time `json:"last_checked_at,omitempty"`
	LastError          string    `json:"last_error,omitempty"`
	AutoCheckEnabled   bool      `json:"auto_check_enabled"`
}

// IsBlocking reports whether the UI should suppress normal operations
// in this state (full-screen modal, etc.).
func (s State) IsBlocking() bool {
	return s.Stage == StageMustUpdate
}
