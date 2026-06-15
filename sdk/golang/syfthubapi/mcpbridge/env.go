package mcpbridge

import (
	"maps"
	"os"
	"sort"
)

// passthroughEnvKeys are benign host env vars a stdio MCP child needs to run
// (find its interpreter, resolve a cache dir, etc.). Everything else from the
// desktop's environment is withheld so an unrelated host secret in the desktop
// process env never reaches an MCP child. The child's actual credentials come
// from the registry's explicit per-server Env, layered on top.
var passthroughEnvKeys = []string{
	"PATH",
	"HOME",
	"LANG",
	"LC_ALL",
	"TMPDIR",
	"TEMP",
	"TMP",
	// Node/npm-based servers (the common case: `npx -y <server>`).
	"NODE_PATH",
	"NPM_CONFIG_CACHE",
	// Windows process bootstrap.
	"SystemRoot",
	"APPDATA",
	"LOCALAPPDATA",
	"USERPROFILE",
	"ProgramData",
	"ProgramFiles",
	"ComSpec",
	"PATHEXT",
}

// childEnv builds the explicit environment for a stdio MCP child: the
// allowlisted host vars plus the server's declared env (which overrides on
// conflict, and carries the credential). The result is sorted for determinism.
func childEnv(def map[string]string) []string {
	merged := map[string]string{}
	for _, k := range passthroughEnvKeys {
		if v, ok := os.LookupEnv(k); ok {
			merged[k] = v
		}
	}
	maps.Copy(merged, def)
	out := make([]string, 0, len(merged))
	for k, v := range merged {
		out = append(out, k+"="+v)
	}
	sort.Strings(out)
	return out
}
