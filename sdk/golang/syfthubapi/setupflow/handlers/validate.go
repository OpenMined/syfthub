package handlers

import (
	"fmt"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// requireTypedConfig returns a structured error if a step's type-specific
// config is nil. Centralizes the nil-check shared by every step handler.
func requireTypedConfig(step *nodeops.SetupStep, typeName string, has bool) error {
	if !has {
		return fmt.Errorf("%s config is required for type '%s'", typeName, typeName)
	}
	return nil
}
