# CLI Simplification Tasks

Five independently schedulable tasks for future simplify agents. Each task is self-contained with file paths, line numbers, specs, and acceptance criteria.

Task 2 should precede Task 3 if tackled by the same agent, since Task 3's migration uses Task 2's helpers.

---

## Task 1 — Extract SDK client construction helper

### Context
Seven call sites build a `syfthub.Client` by hand-assembling the same `[]syfthub.Option` slice. Two of them additionally apply an aggregator alias. This duplication has caused config-field drift risk (`cfg.Timeout` → `time.Duration` conversion is repeated, and only some sites call `cfg.HasAPIToken()` before appending the token).

**Files to create:**
- `cli/internal/clientutil/client.go` (new package)

**Files to modify:**
- `cli/internal/cmd/ls.go:52-60`
- `cli/internal/cmd/whoami.go:45-49`
- `cli/internal/cmd/login.go:76-79`
- `cli/internal/cmd/query.go:65-79` (also passes aggregator alias)
- `cli/internal/cmd/agent.go:118-131` (also passes aggregator alias)
- `cli/internal/cmd/node_run.go:56-58`
- `cli/internal/completion/completion.go:66-75` (uses a fixed 10s timeout instead of `cfg.Timeout` — preserve that behavior)

### Spec
Create:

```go
package clientutil

import (
    "time"
    syfthub "github.com/OpenMined/syfthub/sdk/golang/syfthub"
    "github.com/OpenMined/syfthub/cli/internal/nodeconfig"
)

// NewClient builds a syfthub.Client from config. If aggregatorAlias is non-empty,
// the aggregator URL resolved from cfg.GetAggregatorURL(aggregatorAlias) is applied.
// If timeoutOverride > 0, it is used instead of cfg.Timeout.
func NewClient(cfg *nodeconfig.NodeConfig, aggregatorAlias string, timeoutOverride time.Duration, extra ...syfthub.Option) (*syfthub.Client, error)
```

Also add a method `(c *NodeConfig) TimeoutDuration() time.Duration` to `cli/internal/nodeconfig/config.go` (next to the other helpers near line 209) returning `time.Duration(c.Timeout) * time.Second` with a zero-guard.

### Migration for each site
Replace the 5–10-line options block + `NewClient` call with one call to `clientutil.NewClient(cfg, "", 0)` (or with aggregator alias / fixed timeout where applicable). `query.go` and `agent.go` pass the aggregator alias variable they already compute. `completion.go` passes `10*time.Second` as the override.

### Acceptance
- `go build ./...` and `go vet ./...` clean.
- All seven call sites call `clientutil.NewClient`; no `syfthub.NewClient` invocations remain outside `clientutil`.
- No behavior change for any command (including completion's fixed 10s timeout).

---

## Task 2 — Consolidate JSON-vs-text error/success reporting

### Context
101 occurrences across 18 files repeat this pattern:

```go
if <flag>JSONOutput {
    output.JSON(map[string]interface{}{"status": "error", "message": err.Error()})
} else {
    output.Error("Failed to ...: %v", err)
}
```

Same for success envelopes. Hotspots: `node_endpoint.go` (11), `node_endpoint_log.go`, `add.go` (6), `update_aliases.go` (8), `remove.go` (6), `node_policy.go` (7), `node_init.go` (8), `login.go` (5), `logout.go`, `config.go` (6), `list_aliases.go` (2), `whoami.go` (4), `ls.go`, `query.go`, `node_status.go`, `node_stop.go` (5), `node_endpoint_setup.go` (8), `node_endpoint_setup_init.go` (8).

**Files to modify:**
- `cli/internal/output/output.go` (add helpers near existing `Error` at line 84)
- All files listed above.

### Spec
In `cli/internal/output/output.go`, add:

```go
// Status constants for JSON envelopes.
const (
    StatusSuccess = "success"
    StatusError   = "error"
)

// ReplyError emits a JSON error envelope when jsonMode is true; otherwise prints
// the formatted error to stderr via Error. Returns an error suitable for RunE
// with message formatted via fmt.Errorf(format, args...).
func ReplyError(jsonMode bool, format string, args ...any) error {
    msg := fmt.Sprintf(format, args...)
    if jsonMode {
        JSON(map[string]any{"status": StatusError, "message": msg})
    } else {
        Error("%s", msg)
    }
    return errors.New(msg)
}

// ReplyErrorSoft is ReplyError but returns nil (matches current behavior at
// call sites that report the error but return nil to avoid double-printing).
func ReplyErrorSoft(jsonMode bool, format string, args ...any) {
    ...
}

// ReplySuccess emits a JSON success envelope (merging fields) when jsonMode
// is true; otherwise prints the text message via Success.
func ReplySuccess(jsonMode bool, fields map[string]any, textFormat string, args ...any) {
    if jsonMode {
        out := map[string]any{"status": StatusSuccess}
        for k, v := range fields {
            out[k] = v
        }
        JSON(out)
    } else {
        Success(textFormat, args...)
    }
}
```

### Migration rules
Walk each call site and replace. Two patterns exist:
1. Error then `return err` → use `ReplyError` (returns the error).
2. Error then `return nil` (user-input validation) → use `ReplyErrorSoft`.

Replace every `map[string]interface{}{"status": "success", ...}` literal with `ReplySuccess(jsonMode, map[string]any{...}, "text msg", args...)` — move the non-status fields into the fields map.

Replace every literal `"status"`, `"success"`, `"error"` string key/value in the touched files with the new `output.StatusSuccess` / `output.StatusError` constants.

### Acceptance
- `go build ./...` and `go vet ./...` clean.
- Grep for `"status":\s*"error"` and `"status":\s*"success"` across `cli/internal/` returns 0 hits in command files (only allowed in `output/output.go`).
- JSON output shape for every command is byte-identical to before (test a few by running `syft <cmd> --json` and diffing).

---

## Task 3 — Refactor add/update/list/remove aliases into a generic alias store

### Context
Eight Run functions in four files (`add.go`, `update_aliases.go`, `list_aliases.go`, `remove.go`) implement the same CRUD logic against two different maps on `config.NodeConfig`:
- `cfg.Aggregators map[string]AggregatorConfig` + `cfg.DefaultAggregator string`
- `cfg.AccountingServices map[string]AccountingConfig` + `cfg.DefaultAccounting string`

`AggregatorConfig` and `AccountingConfig` (defined in `cli/internal/nodeconfig/config.go:80,85`) both have identical structure: a single `URL string` field. The four files total ~600 LOC that could collapse to ~200.

**Files to modify:**
- `cli/internal/cmd/add.go` (164 LOC)
- `cli/internal/cmd/update_aliases.go` (189 LOC)
- `cli/internal/cmd/list_aliases.go` (113 LOC)
- `cli/internal/cmd/remove.go` (141 LOC)

### Spec
Introduce an internal `aliasKind` abstraction:

```go
type aliasKind struct {
    name       string // "aggregator" / "accounting service"
    jsonKey    string // "aggregators" / "accounting_services"
    tableTitle string // "Aggregator" / "Accounting"
    get        func(cfg *config.NodeConfig) map[string]string // returns alias -> URL
    set        func(cfg *config.NodeConfig, alias, url string)
    delete     func(cfg *config.NodeConfig, alias string)
    getDefault func(cfg *config.NodeConfig) string
    setDefault func(cfg *config.NodeConfig, alias string)
}

var aggregatorKind = aliasKind{...}
var accountingKind = aliasKind{...}
```

Then implement `runAddAlias(k aliasKind, alias, url string, setDefault, jsonMode bool) error` and similar for update/list/remove. Each Cobra subcommand's `RunE` becomes a 1-line wrapper.

Use `output.ReplyError` / `ReplySuccess` helpers from Task 2 (do Task 2 first if tackling both).

### Acceptance
- `go build ./...` and `go vet ./...` clean.
- `add.go`, `update_aliases.go`, `list_aliases.go`, `remove.go` combined ≤ 400 LOC.
- All eight subcommands (`syft add aggregator|accounting`, `update`, `list`, `remove`) behave identically: same text and JSON output, same exit codes, same error messages.
- Flag surface unchanged: `--default/-d`, `--url/-u`, `--json`.

---

## Task 4 — Extract JSONL scanning in node_endpoint_log.go

### Context
`cli/internal/cmd/node_endpoint_log.go` duplicates the bufio.Scanner + 1 MiB buffer + `json.Unmarshal(line, &logEntry)` pattern three times:
- lines 177-193 inside `followEndpointLogs` (initial catch-up read)
- lines 219-235 inside `followEndpointLogs` (poll loop)
- lines 336-349 inside `readLogFile`

All three allocate a 1 MiB buffer per file open. `followEndpointLogs` does this every 500 ms forever, producing ~1 MB/s of garbage while idle.

**Files to modify:**
- `cli/internal/cmd/node_endpoint_log.go`

### Spec
Add a helper in the same file:

```go
// scanJSONL calls fn for each decoded log entry in r. Lines that fail to
// unmarshal are skipped silently (matches prior behavior). Raw line bytes are
// passed to fn alongside the parsed entry so callers can emit raw JSON mode
// without re-marshaling.
func scanJSONL(r io.Reader, fn func(line []byte, entry *logEntry)) error {
    scanner := bufio.NewScanner(r)
    scanner.Buffer(jsonlBuf[:], len(jsonlBuf))
    for scanner.Scan() {
        line := scanner.Bytes()
        if len(line) == 0 {
            continue
        }
        var e logEntry
        if json.Unmarshal(line, &e) != nil {
            continue
        }
        fn(line, &e)
    }
    return scanner.Err()
}
```

Then for the tail-follow hot path, hoist the 1 MiB buffer to a package-level `var jsonlBuf [1 << 20]byte` so `followEndpointLogs` stops allocating 2 MB/s. Safe because `followEndpointLogs` is single-goroutine. For `readLogFile` (concurrent-safe path), allocate locally.

Refactor `followEndpointLogs` so it opens the file once per date and keeps the handle across polls; reopen only on date rollover or on read error. On each tick, seek from saved offset, scan to EOF, record new offset, leave file open.

### Acceptance
- `go build ./...` and `go vet ./...` clean.
- Only one `json.Unmarshal(line, &entry)` call remains in `node_endpoint_log.go`.
- `syft node endpoint log <slug> -f` produces identical output as before (both JSON and text modes).
- On idle follow, running `strace -c -p <pid>` shows ~1 `read` per 500 ms poll, not `openat + read + close`.

---

## Task 5 — Fix `IsBinaryInstall` dead-logic

### Context
`cli/internal/update/update.go:322-352`. The function checks typical binary directories, then checks `$HOME` prefix, but regardless of results it falls through to `return true // Default to true for most cases`. Every check is dead. The branch at `PerformSelfUpdate:391` that handles "not a binary install" is unreachable.

The intended semantics (from the comment and the fallback branch message): `IsBinaryInstall()` should be `false` when the CLI was installed via `go install` (lives under `$GOPATH/bin` or `$GOBIN`), and `true` when installed to `/usr/local/bin`, `/usr/bin`, `/opt/homebrew/bin`, or a subdirectory of `$HOME/bin` via the install script.

**Files to modify:**
- `cli/internal/update/update.go:322-352`

### Spec
Reimplement as:

```go
func IsBinaryInstall() bool {
    exe, err := os.Executable()
    if err != nil {
        return false
    }
    exe, err = filepath.EvalSymlinks(exe)
    if err != nil {
        return false
    }
    dir := filepath.Dir(exe)

    // Exclude go-install locations: GOBIN or GOPATH/bin.
    if gobin := os.Getenv("GOBIN"); gobin != "" && dir == gobin {
        return false
    }
    if gopath := os.Getenv("GOPATH"); gopath != "" {
        if dir == filepath.Join(gopath, "bin") {
            return false
        }
    }
    if home := os.Getenv("HOME"); home != "" {
        if dir == filepath.Join(home, "go", "bin") {
            return false
        }
    }

    // Accept well-known install-script targets and any $HOME/bin subtree.
    systemBins := []string{"/usr/local/bin", "/usr/bin", "/opt/homebrew/bin"}
    for _, d := range systemBins {
        if dir == d {
            return true
        }
    }
    if home := os.Getenv("HOME"); home != "" {
        if strings.HasPrefix(dir, filepath.Join(home, ".local", "bin")) ||
            strings.HasPrefix(dir, filepath.Join(home, "bin")) ||
            strings.HasPrefix(dir, filepath.Join(home, ".syfthub")) {
            return true
        }
    }
    return false
}
```

Verify against `cli/install.sh` which target path it actually uses — align the accepted directories with that script's install destination.

### Acceptance
- `go build ./...` and `go vet ./...` clean.
- No `return true // Default to true` fallback; every path has an explicit reason.
- Manually: build with `go install` and confirm `syft upgrade` prints the "not a binary install" message. Build with `install.sh` and confirm self-update proceeds.
