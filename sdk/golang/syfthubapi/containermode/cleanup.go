package containermode

import (
	"context"
	"log/slog"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// CleanupOrphans removes containers from previous SyftAPI instances that were
// not properly cleaned up (e.g., due to a crash or SIGKILL). It uses label
// filtering to identify managed containers and skips those belonging to the
// current instance. This function is best-effort: errors are logged but never
// returned, so it cannot block startup.
func CleanupOrphans(ctx context.Context, rt syfthubapi.ContainerRuntime, instanceID string, logger *slog.Logger) error {
	// Get all managed containers
	allIDs, err := rt.List(ctx, map[string]string{"syfthub.managed": "true"})
	if err != nil {
		logger.Warn("cleanup: failed to list managed containers", "error", err)
		return nil
	}
	if len(allIDs) == 0 {
		return nil
	}

	// Get containers belonging to current instance
	currentIDs, err := rt.List(ctx, map[string]string{
		"syfthub.managed":  "true",
		"syfthub.instance": instanceID,
	})
	if err != nil {
		logger.Warn("cleanup: failed to list current instance containers", "error", err)
		return nil
	}

	// Build set of current IDs for O(1) lookup
	currentSet := make(map[string]bool, len(currentIDs))
	for _, id := range currentIDs {
		currentSet[id] = true
	}

	// Remove orphans
	cleaned := 0
	for _, id := range allIDs {
		if currentSet[id] {
			continue
		}
		logger.Info("cleanup: removing orphaned container", "id", id)
		_ = rt.Stop(ctx, id)
		_ = rt.Remove(ctx, id)
		cleaned++
	}

	if cleaned > 0 {
		logger.Info("cleanup: removed orphaned containers", "count", cleaned)
	}
	return nil
}
