package containermode

import (
	_ "embed"
	"regexp"
	"testing"
)

//go:embed runner/_protocol.py
var protocolPy string

// protoLine matches `NAME: Final[str] = "value"` (and bare `NAME = "value"`).
var protoLine = regexp.MustCompile(
	`(?m)^([A-Z_][A-Z0-9_]*)\s*(?::\s*Final\[str\]\s*)?=\s*"([^"]+)"`)

func parseProtocolPy(t *testing.T) map[string]string {
	t.Helper()
	out := map[string]string{}
	for _, m := range protoLine.FindAllStringSubmatch(protocolPy, -1) {
		out[m[1]] = m[2]
	}
	if len(out) == 0 {
		t.Fatal("_protocol.py: no constants parsed — regex/source drift?")
	}
	return out
}

// TestProtocolDrift fails the build if Go-side env-var constants and the
// Python runner/_protocol.py module disagree on a name or value. Both
// sides are the wire protocol between the host SDK and the in-container
// server.py / _syft_audit.py.
func TestProtocolDrift(t *testing.T) {
	py := parseProtocolPy(t)

	want := map[string]string{
		"SYFT_HANDLER_ENV":      SyftHandlerEnvEnv,
		"SYFT_ALLOW_SUBPROC":    SyftAllowSubprocEnv,
		"SYFT_WORKSPACE_SCOPE":  SyftWorkspaceScopeEnv,
		"SYFT_SANDBOX_NET":      SyftSandboxNetEnv,
		"SYFT_SUBPROC_ENV":      SyftSubprocEnvEnv,
		"SYFT_ALLOW_SUBPROCESS": SyftAllowSubprocessEnv,
		"SYFT_CODE_DIR":         SyftCodeDirEnv,
		"SYFT_WORKSPACE_DIR":    SyftWorkspaceDirEnv,
		"GUEST_CODE_DIR":        GuestCodeDir,
		"GUEST_WORKSPACE_DIR":   GuestWorkspaceDir,
	}
	for k, v := range want {
		got, ok := py[k]
		if !ok {
			t.Errorf("_protocol.py is missing %s (Go has %q)", k, v)
			continue
		}
		if got != v {
			t.Errorf("drift: Go %s=%q, _protocol.py %s=%q", k, v, k, got)
		}
	}
}
