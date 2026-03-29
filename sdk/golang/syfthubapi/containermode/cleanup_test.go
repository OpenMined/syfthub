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
