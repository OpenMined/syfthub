package cmd

import (
	"testing"
)

func TestKillOrphanedNodes_NoPanic(t *testing.T) {
	// killOrphanedNodes reads /proc and kills stale "syft node run" processes.
	// This test verifies it doesn't panic when no orphans exist.
	// On non-Linux systems (or in test environments), it should gracefully
	// return early when /proc isn't available.
	killOrphanedNodes()
}
