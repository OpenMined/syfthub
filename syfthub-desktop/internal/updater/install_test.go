package updater

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

type installEmits struct {
	events []InstallState
}

func (e *installEmits) EmitInstall(s InstallState) {
	e.events = append(e.events, s)
}

func (e *installEmits) Last() InstallState {
	if len(e.events) == 0 {
		return InstallState{}
	}
	return e.events[len(e.events)-1]
}

func TestInstallHashMismatchRefuses(t *testing.T) {
	if !inPlaceSupported() {
		t.Skip("in-place install not supported on this platform")
	}
	dir := t.TempDir()
	em := &installEmits{}
	inst := NewInstaller(dir, em, nopLogger{})

	// Create a fake artifact with known sha.
	artifactPath := filepath.Join(dir, "fake")
	body := []byte("hello")
	if err := os.WriteFile(artifactPath, body, 0o644); err != nil {
		t.Fatal(err)
	}

	wrongHash := "0000000000000000000000000000000000000000000000000000000000000000"
	err := inst.Install(context.Background(), "0.2.0", artifactPath, wrongHash, nil, nil)
	if !errors.Is(err, ErrChecksumMismatch) {
		t.Fatalf("want ErrChecksumMismatch, got %v", err)
	}
	if em.Last().Stage != InstallFailed {
		t.Errorf("last stage = %v, want failed", em.Last().Stage)
	}
}

func TestInstallNoArtifactRefuses(t *testing.T) {
	if !inPlaceSupported() {
		t.Skip("in-place install not supported on this platform")
	}
	inst := NewInstaller(t.TempDir(), nil, nopLogger{})
	err := inst.Install(context.Background(), "0.2.0", "", "x", nil, nil)
	if !errors.Is(err, ErrNoDownloadedArtifact) {
		t.Errorf("want ErrNoDownloadedArtifact, got %v", err)
	}
}

func TestInstallSingleInFlight(t *testing.T) {
	inst := NewInstaller(t.TempDir(), nil, nopLogger{})
	// Force inFlight to true to simulate ongoing install.
	if !inst.inFlight.CompareAndSwap(false, true) {
		t.Fatal("expected CAS to succeed initially")
	}
	defer inst.inFlight.Store(false)

	err := inst.Install(context.Background(), "0.2.0", "/tmp/x", "x", nil, nil)
	if !errors.Is(err, ErrInstallInProgress) {
		t.Errorf("want ErrInstallInProgress, got %v", err)
	}
}

func TestLaunchStateRoundTrip(t *testing.T) {
	dir := t.TempDir()
	s := launchState{
		LastInstallVersion: "0.2.0",
		InstallTime:        time.Date(2026, 5, 13, 12, 0, 0, 0, time.UTC),
		BootAttempts:       2,
		LastCleanBootAt:    time.Date(2026, 5, 13, 11, 0, 0, 0, time.UTC),
	}
	if err := writeLaunchState(dir, s); err != nil {
		t.Fatal(err)
	}
	got, err := readLaunchState(dir)
	if err != nil {
		t.Fatal(err)
	}
	if got.LastInstallVersion != s.LastInstallVersion {
		t.Errorf("got %v, want %v", got, s)
	}
	if got.BootAttempts != s.BootAttempts {
		t.Errorf("boot attempts: got %d, want %d", got.BootAttempts, s.BootAttempts)
	}
}

func TestBootGuardTriggersRollback(t *testing.T) {
	dir := t.TempDir()

	// Seed: an install with BootAttempts already at the threshold and
	// no clean boot since.
	installTime := time.Now().UTC().Add(-1 * time.Hour)
	_ = writeLaunchState(dir, launchState{
		LastInstallVersion: "0.2.0",
		InstallTime:        installTime,
		BootAttempts:       MaxBootAttempts,
		LastCleanBootAt:    installTime.Add(-2 * time.Hour),
	})

	guard := NewBootGuard(dir, "")
	if !guard.OnLaunch() {
		t.Error("OnLaunch should request rollback at MaxBootAttempts")
	}
}

func TestBootGuardCleanBootResetsCounter(t *testing.T) {
	dir := t.TempDir()
	_ = writeLaunchState(dir, launchState{
		LastInstallVersion: "0.2.0",
		InstallTime:        time.Now().UTC(),
		BootAttempts:       2,
	})
	guard := NewBootGuard(dir, "")
	guard.MarkCleanBoot()
	got, _ := readLaunchState(dir)
	if got.BootAttempts != 0 {
		t.Errorf("BootAttempts = %d, want 0", got.BootAttempts)
	}
	if got.LastCleanBootAt.IsZero() {
		t.Error("LastCleanBootAt should be set after MarkCleanBoot")
	}
}

// Ensure we don't accidentally enable rollback when there's no install
// history (e.g., a fresh install).
func TestBootGuardNoInstallNoRollback(t *testing.T) {
	dir := t.TempDir()
	guard := NewBootGuard(dir, "")
	if guard.OnLaunch() {
		t.Error("rollback should not trigger without install history")
	}
}
