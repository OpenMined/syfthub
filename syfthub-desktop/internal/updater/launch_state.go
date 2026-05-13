package updater

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// launchState is the rollback-bookkeeping persisted to disk after every
// install and updated on each launch.
type launchState struct {
	LastInstallVersion string    `json:"last_install_version,omitempty"`
	InstallTime        time.Time `json:"install_time,omitempty"`
	BootAttempts       int       `json:"boot_attempts,omitempty"`
	LastCleanBootAt    time.Time `json:"last_clean_boot_at,omitempty"`
}

func launchStatePath(dir string) string {
	return filepath.Join(dir, LaunchStateFileName)
}

func readLaunchState(dir string) (launchState, error) {
	data, err := os.ReadFile(launchStatePath(dir))
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return launchState{}, nil
		}
		return launchState{}, err
	}
	var s launchState
	if err := json.Unmarshal(data, &s); err != nil {
		// Corrupt file: pretend it doesn't exist. The next clean boot
		// will rewrite it.
		return launchState{}, nil
	}
	return s, nil
}

func writeLaunchState(dir string, s launchState) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create launch-state dir: %w", err)
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	tmp := launchStatePath(dir) + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, launchStatePath(dir))
}

// BootGuard implements the rollback heuristic. Called early in main.go
// (before Wails starts), it returns the path to roll back to if the
// previous install is failing repeatedly.
//
//   - On launch: BootAttempts++
//   - After MinCleanBootSeconds of successful runtime: MarkCleanBoot
//   - If on startup BootAttempts >= MaxBootAttempts AND LastCleanBootAt < InstallTime,
//     the heuristic returns a rollback request.
type BootGuard struct {
	dir   string
	exe   string
	state launchState
}

func NewBootGuard(launchStateDir, exePath string) *BootGuard {
	return &BootGuard{dir: launchStateDir, exe: exePath}
}

// OnLaunch increments BootAttempts and returns true if rollback should
// occur. When true, the caller MUST exec the .old binary instead of
// proceeding.
func (g *BootGuard) OnLaunch() (rollback bool) {
	s, _ := readLaunchState(g.dir)
	g.state = s

	if s.LastInstallVersion == "" {
		return false
	}
	// If the most recent install has not been confirmed by a clean boot
	// AND we've hit the attempt threshold, request rollback.
	needsRollback := s.BootAttempts >= MaxBootAttempts && s.LastCleanBootAt.Before(s.InstallTime)

	// Always increment attempts for the current launch. The clean-boot
	// callback will reset this counter if/when the boot succeeds.
	s.BootAttempts++
	_ = writeLaunchState(g.dir, s)

	return needsRollback
}

// MarkCleanBoot records that the current process has run successfully
// long enough to be considered "good". Resets BootAttempts.
func (g *BootGuard) MarkCleanBoot() {
	s, _ := readLaunchState(g.dir)
	s.LastCleanBootAt = time.Now().UTC()
	s.BootAttempts = 0
	_ = writeLaunchState(g.dir, s)
}

// PerformRollback attempts to restore the .old (Linux) / .old.exe
// (Windows) binary. Returns the path to the binary that should be
// exec'd, or an error if no rollback target exists.
func PerformRollback(exePath string) (string, error) {
	candidates := []string{exePath + ".old"}
	if len(exePath) > 4 && exePath[len(exePath)-4:] == ".exe" {
		base := exePath[:len(exePath)-4]
		candidates = append(candidates, base+".old.exe")
	} else {
		candidates = append(candidates, exePath+".old.exe")
	}

	var oldPath string
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			oldPath = c
			break
		}
	}
	if oldPath == "" {
		return "", errors.New("no rollback binary found")
	}

	badPath := exePath + ".bad"
	_ = os.Remove(badPath) // clear any stale .bad
	if err := os.Rename(exePath, badPath); err != nil {
		return "", fmt.Errorf("move bad binary aside: %w", err)
	}
	if err := os.Rename(oldPath, exePath); err != nil {
		// Try to undo
		_ = os.Rename(badPath, exePath)
		return "", fmt.Errorf("restore .old: %w", err)
	}
	return exePath, nil
}
