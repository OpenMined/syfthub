package containermode

import (
	"strings"
	"testing"
)

func TestProbeScript_Embedded(t *testing.T) {
	if len(probeScript) == 0 {
		t.Fatal("probeScript is empty — probe.sh not embedded")
	}
	if !strings.Contains(string(probeScript), "bwrap") {
		t.Errorf("probe.sh missing bwrap invocation")
	}
	if !strings.Contains(string(probeScript), "syft_runtime") {
		t.Errorf("probe.sh does not import the in-bwrap runtime modules")
	}
}

func TestAcceptedSandboxVersions_HasCurrent(t *testing.T) {
	if _, ok := AcceptedSandboxVersions[currentSandboxVersion]; !ok {
		t.Errorf("current version %q must be in AcceptedSandboxVersions",
			currentSandboxVersion)
	}
}

func TestTrimTail(t *testing.T) {
	cases := []struct {
		in, want string
		n        int
	}{
		{"short", "short", 100},
		{"abcdefghij", "...defghij", 7},
		{"", "", 5},
	}
	for _, c := range cases {
		got := trimTail(c.in, c.n)
		if got != c.want {
			t.Errorf("trimTail(%q, %d) = %q, want %q", c.in, c.n, got, c.want)
		}
	}
}

func TestHintForExitCode(t *testing.T) {
	cases := []struct {
		name     string
		code     int
		stderr   string
		contains string
	}{
		{"missing bwrap", 10, "", "missing bubblewrap"},
		{"userns disabled", 11, "", "unprivileged user namespaces"},
		{"runtime missing", 12, "", "syfthub/endpoint-runner"},
		{"python too old", 13, "", "Python 3.9+"},
		{"legacy entrypoint", -1, "__main__.py: error: unrecognized arguments: -s\n", "stale"},
		{"unknown", -1, "some other error", "docs/architecture/sandbox.md"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := hintForExitCode(c.code, c.stderr)
			if !strings.Contains(got, c.contains) {
				t.Errorf("hintForExitCode(%d, %q) = %q, want it to contain %q",
					c.code, c.stderr, got, c.contains)
			}
		})
	}
}
