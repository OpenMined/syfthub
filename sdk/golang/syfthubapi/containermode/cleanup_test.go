package containermode

import (
	"context"
	"log/slog"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// mockRuntime implements syfthubapi.ContainerRuntime for testing.
type mockRuntime struct {
	listResults map[string][]string // key: sorted labels string, value: IDs
	stopCalls   []string
	removeCalls []string
	stopErr     error
}

func (m *mockRuntime) Create(_ context.Context, _ any) (string, error) { return "", nil }
func (m *mockRuntime) Start(_ context.Context, _ string) error         { return nil }
func (m *mockRuntime) Stop(_ context.Context, id string) error {
	m.stopCalls = append(m.stopCalls, id)
	return m.stopErr
}
func (m *mockRuntime) Remove(_ context.Context, id string) error {
	m.removeCalls = append(m.removeCalls, id)
	return nil
}
func (m *mockRuntime) List(_ context.Context, labels map[string]string) ([]string, error) {
	// Match based on number of labels (simple heuristic for test)
	if len(labels) == 1 {
		return m.listResults["all"], nil
	}
	return m.listResults["current"], nil
}
func (m *mockRuntime) GetHostPort(_ context.Context, _ string, _ string) (string, error) {
	return "0", nil
}
func (m *mockRuntime) Inspect(_ context.Context, _ string) (*syfthubapi.ContainerInfo, error) {
	return &syfthubapi.ContainerInfo{}, nil
}
func (m *mockRuntime) Logs(_ context.Context, _ string, _ int) (string, error) {
	return "", nil
}

var _ syfthubapi.ContainerRuntime = (*mockRuntime)(nil)

func TestCleanupOrphans_RemovesOrphans(t *testing.T) {
	rt := &mockRuntime{
		listResults: map[string][]string{
			"all":     {"aaa", "bbb", "ccc"},
			"current": {"bbb"},
		},
	}

	err := CleanupOrphans(context.Background(), rt, "test-instance", slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}

	if len(rt.stopCalls) != 2 {
		t.Fatalf("expected 2 stop calls, got %d: %v", len(rt.stopCalls), rt.stopCalls)
	}
	if len(rt.removeCalls) != 2 {
		t.Fatalf("expected 2 remove calls, got %d: %v", len(rt.removeCalls), rt.removeCalls)
	}
}

func TestCleanupOrphans_NoOrphans(t *testing.T) {
	rt := &mockRuntime{
		listResults: map[string][]string{
			"all":     {"aaa"},
			"current": {"aaa"},
		},
	}

	err := CleanupOrphans(context.Background(), rt, "test-instance", slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}

	if len(rt.stopCalls) != 0 {
		t.Fatalf("expected 0 stop calls, got %d", len(rt.stopCalls))
	}
}

func TestCleanupOrphans_ErrorsDoNotPropagate(t *testing.T) {
	rt := &mockRuntime{
		listResults: map[string][]string{
			"all":     {"aaa", "bbb"},
			"current": {"bbb"},
		},
		stopErr: context.DeadlineExceeded,
	}

	err := CleanupOrphans(context.Background(), rt, "test-instance", slog.Default())
	if err != nil {
		t.Fatalf("cleanup errors should not propagate, got %v", err)
	}
}

func TestCleanupOrphans_EmptyList(t *testing.T) {
	rt := &mockRuntime{
		listResults: map[string][]string{
			"all":     {},
			"current": {},
		},
	}

	err := CleanupOrphans(context.Background(), rt, "test-instance", slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}
}

func TestCleanupOrphans_AllBelongToCurrentInstance(t *testing.T) {
	rt := &mockRuntime{
		listResults: map[string][]string{
			"all":     {"aaa", "bbb", "ccc"},
			"current": {"aaa", "bbb", "ccc"},
		},
	}

	err := CleanupOrphans(context.Background(), rt, "test-instance", slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}

	if len(rt.stopCalls) != 0 {
		t.Fatalf("expected 0 stop calls when all containers belong to current instance, got %d", len(rt.stopCalls))
	}
	if len(rt.removeCalls) != 0 {
		t.Fatalf("expected 0 remove calls, got %d", len(rt.removeCalls))
	}
}

func TestCleanupOrphans_ListErrorReturnsNil(t *testing.T) {
	rt := &mockRuntimeWithListError{
		listErr: context.DeadlineExceeded,
	}

	err := CleanupOrphans(context.Background(), rt, "test-instance", slog.Default())
	if err != nil {
		t.Fatalf("list errors should not propagate, got %v", err)
	}
}

func TestCleanupOrphans_RemovesCorrectOrphanIDs(t *testing.T) {
	rt := &mockRuntime{
		listResults: map[string][]string{
			"all":     {"orphan1", "current1", "orphan2", "current2"},
			"current": {"current1", "current2"},
		},
	}

	err := CleanupOrphans(context.Background(), rt, "my-instance", slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}

	if len(rt.stopCalls) != 2 {
		t.Fatalf("expected 2 stop calls, got %d: %v", len(rt.stopCalls), rt.stopCalls)
	}

	// Verify the correct IDs were stopped
	stoppedSet := make(map[string]bool)
	for _, id := range rt.stopCalls {
		stoppedSet[id] = true
	}
	if !stoppedSet["orphan1"] || !stoppedSet["orphan2"] {
		t.Errorf("expected orphan1 and orphan2 to be stopped, got: %v", rt.stopCalls)
	}
	if stoppedSet["current1"] || stoppedSet["current2"] {
		t.Error("current instance containers should not be stopped")
	}
}

func TestCleanupOrphans_SingleOrphan(t *testing.T) {
	rt := &mockRuntime{
		listResults: map[string][]string{
			"all":     {"orphan1"},
			"current": {},
		},
	}

	err := CleanupOrphans(context.Background(), rt, "test-instance", slog.Default())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}

	if len(rt.stopCalls) != 1 {
		t.Fatalf("expected 1 stop call, got %d", len(rt.stopCalls))
	}
	if rt.stopCalls[0] != "orphan1" {
		t.Errorf("expected to stop 'orphan1', got %q", rt.stopCalls[0])
	}
}

// mockRuntimeWithListError always returns an error from List.
type mockRuntimeWithListError struct {
	listErr error
}

func (m *mockRuntimeWithListError) Create(_ context.Context, _ any) (string, error) { return "", nil }
func (m *mockRuntimeWithListError) Start(_ context.Context, _ string) error         { return nil }
func (m *mockRuntimeWithListError) Stop(_ context.Context, _ string) error          { return nil }
func (m *mockRuntimeWithListError) Remove(_ context.Context, _ string) error        { return nil }
func (m *mockRuntimeWithListError) List(_ context.Context, _ map[string]string) ([]string, error) {
	return nil, m.listErr
}
func (m *mockRuntimeWithListError) GetHostPort(_ context.Context, _ string, _ string) (string, error) {
	return "0", nil
}
func (m *mockRuntimeWithListError) Inspect(_ context.Context, _ string) (*syfthubapi.ContainerInfo, error) {
	return &syfthubapi.ContainerInfo{}, nil
}
func (m *mockRuntimeWithListError) Logs(_ context.Context, _ string, _ int) (string, error) {
	return "", nil
}
