// Package version provides version information for the CLI.
// The version is set at build time via ldflags.
package version

// Version is the CLI version, set at build time via:
// go build -ldflags "-X github.com/OpenMined/syfthub/cli/internal/version.Version=1.0.0"
var Version = "dev"
