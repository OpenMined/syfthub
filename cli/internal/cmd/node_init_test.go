package cmd

import (
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

func TestPkgDisplayType(t *testing.T) {
	tests := []struct {
		name string
		pkg  nodeops.MarketplacePackage
		want string
	}{
		{
			name: "agent tag overrides type",
			pkg: nodeops.MarketplacePackage{
				Type: "model",
				Tags: []string{"agent"},
			},
			want: "agent",
		},
		{
			name: "agent tag among others",
			pkg: nodeops.MarketplacePackage{
				Type: "model",
				Tags: []string{"ml", "agent", "chat"},
			},
			want: "agent",
		},
		{
			name: "model type without agent tag",
			pkg: nodeops.MarketplacePackage{
				Type: "model",
				Tags: []string{"ml", "chat"},
			},
			want: "model",
		},
		{
			name: "data_source type",
			pkg: nodeops.MarketplacePackage{
				Type: "data_source",
				Tags: []string{"csv"},
			},
			want: "data_source",
		},
		{
			name: "no tags uses type",
			pkg: nodeops.MarketplacePackage{
				Type: "model",
				Tags: nil,
			},
			want: "model",
		},
		{
			name: "empty tags uses type",
			pkg: nodeops.MarketplacePackage{
				Type: "data_source",
				Tags: []string{},
			},
			want: "data_source",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := pkgDisplayType(tt.pkg)
			if got != tt.want {
				t.Errorf("pkgDisplayType() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestKillOrphanedNodes_NoPanic(t *testing.T) {
	// killOrphanedNodes reads /proc and kills stale "syft node run" processes.
	// This test verifies it doesn't panic when no orphans exist.
	// On non-Linux systems (or in test environments), it should gracefully
	// return early when /proc isn't available.
	killOrphanedNodes()
}
