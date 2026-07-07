package setupflow

import (
	"fmt"
	"path/filepath"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// mergeEnvFile reads the existing .env, applies updates (add or replace keys),
// and writes it back. Preserves ordering of existing keys.
// New keys are appended at the end.
func mergeEnvFile(endpointDir string, updates map[string]string) error {
	envPath := filepath.Join(endpointDir, ".env")

	// Read existing env vars
	existing, err := nodeops.ReadEnvFile(envPath)
	if err != nil {
		return fmt.Errorf("failed to read .env: %w", err)
	}

	// Build map for quick lookup
	updated := make(map[string]bool)

	// Update existing keys in place
	var result []nodeops.EnvVar
	for _, ev := range existing {
		if newVal, ok := updates[ev.Key]; ok {
			result = append(result, nodeops.EnvVar{Key: ev.Key, Value: newVal})
			updated[ev.Key] = true
		} else {
			result = append(result, ev)
		}
	}

	// Append new keys
	for key, val := range updates {
		if !updated[key] {
			result = append(result, nodeops.EnvVar{Key: key, Value: val})
		}
	}

	return nodeops.WriteEnvFile(envPath, result)
}
