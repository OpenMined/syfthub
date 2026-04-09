package setupflow

import (
	"path/filepath"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// mergeEnvFile reads the existing .env, applies updates (add or replace keys),
// and writes it back. Delegates to nodeops.MergeEnvFile.
func mergeEnvFile(endpointDir string, updates map[string]string) error {
	return nodeops.MergeEnvFile(filepath.Join(endpointDir, ".env"), updates, false)
}
