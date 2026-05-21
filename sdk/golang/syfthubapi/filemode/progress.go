package filemode

// LoadPhase identifies a stage in the endpoint load lifecycle. Phases
// arrive in order per (slug); LoadPhaseReady and LoadPhaseFailed are
// terminal. Container endpoints traverse the full ladder; file-mode
// endpoints only emit LoadPhasePending → LoadPhaseReady (or Failed).
type LoadPhase string

const (
	LoadPhasePending           LoadPhase = "pending"
	LoadPhaseResolvingImage    LoadPhase = "resolving_image"
	LoadPhasePullingImage      LoadPhase = "pulling_image"
	LoadPhaseBuildingImage     LoadPhase = "building_image"
	LoadPhaseVerifyingImage    LoadPhase = "verifying_image"
	LoadPhaseMaterializing     LoadPhase = "materializing"
	LoadPhaseStartingContainer LoadPhase = "starting_container"
	LoadPhaseReady             LoadPhase = "ready"
	LoadPhaseFailed            LoadPhase = "failed"
)

// LoadProgressEvent is delivered to the LoadProgressCallback at each
// phase transition during LoadEndpoints.
type LoadProgressEvent struct {
	Slug    string    `json:"slug"`
	Name    string    `json:"name"`
	Phase   LoadPhase `json:"phase"`
	Message string    `json:"message,omitempty"`
	Error   string    `json:"error,omitempty"`
	Index   int       `json:"index"`
	Total   int       `json:"total"`
}

// LoadProgressCallback receives LoadProgressEvent at each phase
// transition. Container endpoints are built in parallel, so the callback
// MUST be safe for concurrent invocation from multiple goroutines.
type LoadProgressCallback func(LoadProgressEvent)
