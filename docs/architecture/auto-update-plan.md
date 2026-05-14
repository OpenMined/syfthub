# Plan — Auto-update for SyftHub Desktop

**Status:** proposed
**Date:** 2026-05-13
**Scope:** `syfthub-desktop/` (Go + React) + `.github/workflows/release-desktop.yml`
**Related:** `RELEASING.md` (desktop release process), `release-desktop.yml` (current workflow)

## Problem

The desktop app has no auto-update mechanism today. Users re-download from the GitHub Releases page whenever they think to check. Two operational gaps:

1. **No discovery.** A user on `0.1.0` has no way to learn `0.2.0` exists without visiting the releases page. Adoption of fixes is slow.
2. **No floor.** If a critical bug or vulnerability is found in `0.1.x`, there is no way to prevent affected clients from continuing to run.

## Goals

- Notify the user when a new stable version is available (24 h background check + manual "Check now").
- Hard-gate security-critical updates via a `min_supported_version` field — clients below the floor cannot start new operations until they update.
- Provide in-app download with SHA-256 integrity verification (all platforms).
- Provide in-place install on Linux + Windows.
- Provide assisted (manual) install on macOS until code signing is funded.

## Non-goals (explicit)

- **No beta channel.** Stable only.
- **No telemetry.** No update events are reported to the backend.
- **No code signing / notarization.** Tracked separately; blocks macOS in-place update.
- **No new architectures.** macOS Intel, Linux arm64, Windows arm64 still out of scope.

## Constraints (what must not change)

1. `release-desktop.yml` continues to publish the same per-platform binaries + `.sha256` + `checksums.txt`.
2. The `desktop/v*` tag protection rule stays. A new rule covers `desktop/latest-stable`.
3. App shutdown continues to drain node daemon, end agent sessions, close NATS (`OnShutdown` in `main.go:55`).
4. Version stays ldflag-injected (`-X 'main.Version=...'`) — no version file in the repo.
5. No new runtime dependencies beyond `github.com/minio/selfupdate` (Phase 3 only) and `golang.org/x/mod/semver`.

## Architecture

### Manifest distribution

Single canonical URL the client polls:

```
https://github.com/OpenMined/syfthub/releases/download/desktop/latest-stable/manifest.json
```

`desktop/latest-stable` is a pinned, non-versioned GitHub Release. Its only asset is `manifest.json`, overwritten by the release workflow on every successful versioned release via `gh release upload desktop/latest-stable manifest.json --clobber`.

Why this URL:
- Served from `objects.githubusercontent.com` — does not consume the unauth GitHub API 60/h rate limit.
- Single static URL — no tag filtering, no semver re-parsing client-side.
- Workflow-controlled — staged rollout, kill-switch (flip the manifest after a bad build), and hotfix-in-place are all possible without touching versioned releases.
- Distinct from the `desktop/v*` namespace — does not conflict with existing tag protection or `softprops/action-gh-release`'s versioned release flow.

Bootstrap (one-time): a maintainer creates the `desktop/latest-stable` release manually, attaches a placeholder `manifest.json` matching the current shipping version, and adds a tag protection rule for `desktop/latest-stable`. This is documented in `RELEASING.md`.

### Manifest schema

```json
{
  "schema_version": 1,
  "version": "0.2.0",
  "min_supported_version": "0.1.0",
  "published_at": "2026-05-15T12:00:00Z",
  "release_notes_url": "https://github.com/OpenMined/syfthub/releases/tag/desktop/v0.2.0",
  "must_update_reason": null,
  "platforms": {
    "linux/amd64":   { "url": "...syfthub-desktop-linux-amd64",       "sha256": "...", "size_bytes": 12345678 },
    "windows/amd64": { "url": "...syfthub-desktop-windows-amd64.exe", "sha256": "...", "size_bytes": 13456789 },
    "darwin/arm64":  { "url": "...syfthub-desktop-macos-arm64.zip",   "sha256": "...", "size_bytes": 23456789 }
  }
}
```

Field semantics:
- `version`: latest stable available (no `v` prefix, raw semver).
- `min_supported_version`: floor. Clients running below this enter `must_update` state. Default: stays at the version current when `latest-stable` was created. Bumped only by release engineering for security / data-corruption fixes (documented in `RELEASING.md`).
- `must_update_reason`: optional short string (e.g., `"security: CVE-2026-xxxx"`) shown in the blocking modal. `null` when not in a force-update.
- `platforms.<goos>/<goarch>`: per-asset download URL + lowercase hex SHA-256 + size. Platforms missing from the map are treated as "not built for your OS — open the release page."
- `schema_version`: monotonic. Client refuses any manifest with a version it doesn't know how to parse.

### Update state machine

States the client tracks (single value, transitions atomic):

| State | Meaning |
|---|---|
| `idle` | `current >= min_supported` and `current == version`. Nothing to do. |
| `available(v)` | `current >= min_supported` and `current < version`. Dismissable banner shown. |
| `must_update(v, reason)` | `current < min_supported`. Full-screen blocking modal. UI suppressed. |
| `offline_grace` | Manifest unreachable; cached manifest still within TTL. Last known state honored. |
| `offline_no_grace` | Manifest unreachable AND no cached manifest within TTL. Non-blocking warning, app fully functional. |
| `unsupported_platform` | Running on a `goos/goarch` not in `platforms`. Banner directs to release page. |

Transitions:
- App start → 30 s grace → check → state update.
- Ticker every 24 h ± 2 h jitter → check → state update.
- User "Check now" → immediate check.
- Network failure → preserve previous state if cached manifest fresh, else `offline_grace` until TTL expires, then `offline_no_grace`.

The 30 s startup grace is important: the initial check must not block boot, must not block node-daemon launch, and must not block the user from using the app before a network round-trip resolves.

### Hard-gate semantics (`min_supported_version`)

The "block on launch" behavior is the sharpest tool in this design and needs clear rules.

**When the gate bumps:** release engineering only bumps `min_supported_version` when the release fixes (a) a remotely exploitable security issue, (b) a data-corruption or data-loss bug, or (c) a wire-protocol incompatibility that would corrupt peer state. Routine bug fixes and feature releases do not bump the floor.

**What "blocked" means:**
- The Wails window still opens (so the user can see *why* they're blocked and take action).
- `MustUpdateModal` is mounted with `pointer-events: auto` over a dimmed app shell; the underlying tabs/sidebar render but are non-interactive.
- The updater package suppresses startup of: node daemon, new agent sessions, new endpoint subprocesses, new outgoing NATS connections. Existing in-flight operations triggered before the check returned drain normally — we do not yank running work out from under the user.
- The modal exposes only two actions: "Quit" and "Download update". No "Continue at my own risk" — a dismissable security gate is not a security gate.

**Offline tolerance — TTL on cached manifest:**
- Cache lives in `os.UserConfigDir()/syfthub-desktop/manifest-cache.json` with the fetch timestamp.
- TTL is 14 days. While the cache is fresh, the hard-gate uses the cached `min_supported_version`.
- If the cache is older than 14 days *and* the network is unreachable, the gate is suspended (state = `offline_no_grace`, app functional, warning shown). The user is on a generous grace period but not bricked.
- If the cache is fresh and the user is below its floor, the gate applies even offline. This is the property that lets us push out fixes that reach users who have already cached a more recent manifest.

14 days is the trade-off knob. Long enough to cover normal user travel and intermittent GitHub outages, short enough to push a fix to a populated install base within a reasonable window. The TTL is a constant in the client; bumping it requires a release.

**Emergency bypass:** `SYFTHUB_DESKTOP_SKIP_UPDATE_CHECK=1` disables the entire updater (check, banner, gate). Documented in `RELEASING.md` under troubleshooting, not surfaced in the UI.

### Why the gate uses cached state, not just live state

A naive implementation would say "if the manifest fetch fails, the user can do anything." That defeats the gate: an attacker who can DoS the manifest URL (or who is on a network that blocks it) skips the floor. The cached-manifest design means once a client has *ever* learned that the floor is `0.1.5`, going offline doesn't downgrade that knowledge — the gate persists until the cache expires.

---

## Phasing

### Phase 1 — Notify-only + hard-gate

**Workflow changes (`release-desktop.yml`):**

New `manifest` job, runs after `release` succeeds:
1. Re-reads the per-artifact `.sha256` files from the just-published release.
2. Renders `manifest.json` from a template (substituting version, platforms, URLs).
3. `min_supported_version` source: a file in the repo at `syfthub-desktop/.min-supported-version` (single line, semver). Default unchanged across releases unless the maintainer edits it as part of the release PR. This makes the floor a reviewable change in the diff.
4. `gh release upload desktop/latest-stable manifest.json --clobber` to overwrite the manifest asset.

**Client changes — new package `syfthub-desktop/internal/updater`:**

| File | Purpose |
|---|---|
| `manifest.go` | Schema struct, parser, schema_version check |
| `check.go` | Background loop, 30 s startup grace, 24 h ± 2 h jitter, state machine |
| `cache.go` | Disk-backed manifest cache with TTL |
| `semver.go` | Thin wrapper over `golang.org/x/mod/semver` (handles `v` prefix, pre-release ordering) |
| `state.go` | `UpdateState` struct exposed to JS |

**App bindings (`app.go`):**
- `GetUpdateState() UpdateState` — current state snapshot
- `CheckForUpdatesNow() (UpdateState, error)` — immediate check
- `OpenReleaseNotes(url string) error` — wraps `runtime.BrowserOpenURL` with URL validation
- `SetAutoCheckEnabled(bool) error` — persists to settings

**Wails events emitted from the updater goroutine:**
- `update:state` — payload is the current `UpdateState`. Fired on every transition.

**Settings additions (extends `settings.go` + `SettingsContext.tsx`):**
- `auto_check_enabled: bool` (default `true`)
- `last_check_at: time` (informational)

**Frontend:**
- `UpdateContext.tsx` subscribes to `update:state`, exposes hook `useUpdateState()`.
- `UpdateBanner.tsx` — top-of-chrome dismissable strip; visible only in `available` state. "View release notes" → `OpenReleaseNotes`. "Dismiss" hides it until next version.
- `MustUpdateModal.tsx` — full-screen blocking modal; visible in `must_update`. Two actions: Quit (`runtime.Quit`), Download update (Phase 2 — until Phase 2 lands, deep-link to release page).
- `SettingsTab.tsx` adds an "About & Updates" subsection: version, last-checked, "Check now", "Automatic update checks" toggle.

**Pre-release / dev build behavior:**
- If `main.Version == "dev"` or contains a SemVer pre-release suffix (`-alpha`, `-beta`, `-rc`, `-dev`), the updater starts in `disabled` mode — no checks, no banner, no gate. The "About" panel shows current version + "(development build — auto-update disabled)".

**Tests:**
- Manifest parse: valid, missing fields, unknown `schema_version`, malformed sha256, missing current platform.
- Semver compare: pre-releases sort below release; `dev` always behind; equal versions = `idle`.
- Cache: fresh (within TTL), expired, missing, corrupted file (recovered gracefully).
- State machine: every transition; in particular, force-update arriving mid-session must transition `idle → must_update`.
- Network failure modes: timeout, 404 (deleted release), 5xx, body too large, invalid JSON.

**Estimate:** ~1 week including frontend.

---

### Phase 2 — Assisted download (all platforms)

When state is `available` or `must_update`, the banner / modal gains a "Download update" action. The artifact is downloaded, verified, and revealed in the system file browser. User installs manually.

This is the **terminal state for macOS** until Phase 4 (signing) lands.

**Client additions to `internal/updater`:**

| File | Purpose |
|---|---|
| `download.go` | Streaming download with SHA-256 verification, resume support |

- `DownloadUpdate(ctx) error` binding:
  - Resolves the current platform's `(url, sha256, size_bytes)` from the cached manifest.
  - Writes to `os.UserCacheDir()/syfthub-desktop/updates/<version>/<filename>.partial`.
  - Streams the response, hashing as it writes. Hard cap at `size_bytes * 1.05` to bound disk usage.
  - If `.partial` exists from a prior run and matches the manifest size, attempts a `Range:` resume; restarts from zero if the server doesn't honor `Range:`.
  - On `EOF`, verifies the final hash against the manifest. Mismatch deletes the partial and returns an error.
  - Atomic rename `<filename>.partial` → `<filename>` on success.
  - Emits `update:download:progress` (with `bytes_done`, `bytes_total`) at most every 250 ms.
  - Emits `update:download:complete` with the absolute file path.
- Cleanup: on app start, delete any update directories older than the current `available` version.

**Frontend:**
- Banner gains a "Download" button. Click → progress bar inline. Complete → "Reveal in file browser" + "View install instructions" actions.
- "Reveal in file browser": `runtime.BrowserOpenURL("file:///...containing/dir/")` on all platforms. macOS opens Finder, Windows opens Explorer, Linux best-effort opens the default file manager.
- Install instructions are static per-platform strings (mirror what's in the current release notes — drag-to-Applications for macOS, run-the-exe for Windows, `chmod +x && ./binary` for Linux).

**Tests:**
- Resume: kill download mid-way, restart, verify final hash.
- Hash mismatch: serve a corrupted body, assert deletion + error.
- Size cap: serve more than `size_bytes * 1.05`, assert abort.
- Stale download cleanup: pre-create old directories, verify removal.

**Estimate:** ~3 days.

---

### Phase 3 — In-place install (Linux + Windows only)

**New dependency:** `github.com/minio/selfupdate` (MIT, active fork of `inconshreveable/go-update`). It handles the OS-specific binary swap on Linux and Windows correctly, including the Windows `MoveFileEx` rename-while-running dance. Ed25519 verification is supported but unused until Phase 5.

**Client additions:**

| File | Purpose |
|---|---|
| `install.go` | OS-agnostic install orchestrator |
| `install_linux.go` | Linux-specific path resolution |
| `install_windows.go` | Windows-specific path resolution + post-update cleanup hook |
| `install_darwin_stub.go` | Stub: returns "not implemented; use Reveal in Finder" |
| `launch_state.go` | Rollback bookkeeping |

**`InstallUpdate(ctx) error` binding (linux/amd64, windows/amd64 only):**
1. Acquires `installing atomic.Bool`. Concurrent calls return immediately with `ErrInstallInProgress`.
2. Verifies the downloaded artifact's SHA-256 against the manifest *one more time* (manifest may have been refreshed since download).
3. Calls `app.PrepareForUpdate(ctx)`:
   - Sets a flag suppressing new operations (mirrors the must-update gate's suppression list).
   - Cancels in-flight agent sessions via the existing cancellation path in `agent_operations.go`.
   - Stops the node daemon (existing supervisor shutdown).
   - Closes endpoint subprocesses.
   - Closes NATS connections.
   - Flushes settings + setup state to disk.
4. Calls `selfupdate.Apply(downloadedFile, selfupdate.Options{TargetPath: os.Executable()})`. With verification disabled (we already verified the SHA), this:
   - **Linux:** renames the running binary to `<name>.old` (same dir, same FS), writes the new binary under the original name with `0755`.
   - **Windows:** uses `MoveFileEx` to rename `<name>.exe` → `<name>.old.exe` (allowed even with the file in use), writes the new `.exe` under the original name.
5. Updates `launch-state.json` with `last_install_version`, `install_time`, resets `boot_attempts` to 0.
6. `os.StartProcess(currentPath, []string{currentPath, "--post-update"}, ...)` — spawns the new binary detached, with stdin/stdout/stderr detached so the parent can exit cleanly.
7. `runtime.Quit(ctx)` → fires `OnShutdown` → process exits.

**Post-update first launch:**
- `main.go` checks for the `--post-update` flag early. If present, the bootstrap performs the cleanup task (delete sibling `<name>.old` / `<name>.old.exe`) before normal startup proceeds.
- A goroutine in `app.startup` schedules a "successful boot" marker write to `launch-state.json` 30 s after `OnDomReady`. This is the signal the rollback heuristic uses.

**Rollback heuristic:**
- `launch-state.json` tracks: `last_install_version`, `install_time`, `boot_attempts`, `last_clean_boot_at`.
- Bootstrap (in `main.go`, before Wails starts) reads the file. If `last_install_version` matches the current binary's version AND `boot_attempts >= 3` AND `last_clean_boot_at < install_time`, the bootstrap considers the install bad: renames `<name>` back to `<name>.bad`, renames `<name>.old` to `<name>`, re-execs. The crash counter resets; the next launch is on the previous version.
- "Clean boot" definition: app reached `OnDomReady` and ran for ≥30 s.
- This rollback is best-effort and only catches startup crashes (the most common kind of broken release). Runtime-only regressions still ship.

**UX during install:**
- Banner / modal "Install & restart" button → full-screen non-dismissable overlay "Installing update — your session will be restored…"
- On post-update relaunch: brief "Updated to v0.2.0" toast (visible for 5 s, then auto-dismiss).

**Tests:**
- Drain ordering: assert node daemon, agent sessions, NATS are stopped *before* `selfupdate.Apply` is called.
- Single-instance lock: two concurrent `InstallUpdate` calls — only one runs.
- Rollback: simulate 3 startup crashes after an install, assert `.bad` / `.old` swap.
- Path resolution: app launched from `/usr/local/bin/`, `/Applications/`, `~/Applications/`, an arbitrary path.

**Estimate:** ~2 weeks.

---

### Phase 4 — macOS signing + in-place install (deferred)

Tracked separately from this plan. Until code signing + notarization are funded, macOS state machine ends at Phase 2 (download + reveal in Finder). The `must_update` modal on macOS still works — it just routes the user through the manual install path.

Design note for when this lands: the cleanest path is to embed Sparkle (the macOS gold standard) rather than build the `.app`-bundle swap dance ourselves. Sparkle handles the `.app` replace, quarantine xattr stripping, EdDSA signature verification, and relaunch correctly. Wails has no official Sparkle wrapper but the Objective-C bridge is small.

---

### Phase 5 — Manifest signature (future)

After Phase 1 has been in production for a release cycle, sign the manifest itself:
- Generate Ed25519 keypair. Public key embedded as `//go:embed updater/manifest_pubkey.pem` in the client.
- Private key stored in a GitHub Environment-protected secret in a new `desktop` environment (mirrors the existing `pypi` / `npm` environments documented in `RELEASING.md`).
- Workflow signs `manifest.json` → produces `manifest.json.sig` alongside it.
- Client fetches both. Refuses to parse the manifest if the signature is missing, invalid, or against an unknown key.

This closes the "compromised GitHub Actions token" gap. Cheap to add once the manifest pipeline is stable.

The same key can be reused later in Phase 3 to sign the binaries via `minio/selfupdate`'s built-in Ed25519 verification — end-to-end signature chain without depending on Apple/Microsoft signing.

---

## File layout

```
syfthub-desktop/
  .min-supported-version             # single-line semver, source of truth for the floor
  internal/
    updater/
      manifest.go
      check.go
      cache.go
      semver.go
      state.go
      download.go                    # Phase 2
      install.go                     # Phase 3
      install_linux.go               # Phase 3
      install_windows.go             # Phase 3
      install_darwin_stub.go         # Phase 3
      launch_state.go                # Phase 3
      embed/
        manifest_pubkey.pem          # Phase 5
  app.go                             # bindings + start updater goroutine
  main.go                            # Phase 3: handle --post-update flag

frontend/src/
  contexts/
    UpdateContext.tsx
  components/
    UpdateBanner.tsx
    MustUpdateModal.tsx
    UpdateProgress.tsx               # Phase 2
    tabs/
      SettingsTab.tsx                # extended with About & Updates

.github/workflows/
  release-desktop.yml                # new `manifest` job (Phase 1)
```

---

## Phasing summary

| Phase | Effort | Risk | Notes |
|---|---|---|---|
| 1. Notify + hard-gate | ~1 week | Low | Manifest pipeline + UI banner + must-update modal. No binary replacement. |
| 2. Assisted download | ~3 days | Low | All platforms; macOS terminal state. |
| 3. In-place install (Linux/Win) | ~2 weeks | Medium | Drain + swap + rollback. macOS still uses Phase 2 path. |
| 4. macOS signing + Sparkle | TBD | Medium | Blocked on signing funding. |
| 5. Manifest signature | ~3 days | Low | Anytime after Phase 1 stable. |

---

## Open implementation questions

- **Cache path on per-platform reinstall.** `os.UserConfigDir()` survives `.app` re-install on macOS, `%AppData%` on Windows, `~/.config` on Linux — confirm `setup.go`'s existing directory choices are consistent so the cache is preserved across an update.
- **Where the version comparator handles `"dev"`.** Proposal: any version string that fails strict semver parse is treated as "newer than everything" (so `dev` builds never receive an "update available" banner). Tested explicitly.
- **`must_update` mid-session.** The check goroutine may discover a floor bump while the user is mid-conversation with an agent. We deliberately do *not* kill running operations — only block new ones. The modal appears the moment the user tries to start something new, or 10 s after the running operation completes (whichever first). Worth pinning this UX before implementation.
- **Disk reservation.** Should `DownloadUpdate` pre-check `df` for sufficient space and surface a clear error, or just let the write fail? Proposal: pre-check, since the partial-file cleanup path is more annoying than a single check.
- **Manifest job idempotency.** If `release-desktop.yml`'s `manifest` job fails partway, re-running the workflow must produce the same manifest. The job reads SHAs from the already-published assets (not from the `dist/` directory of a particular job), so re-run is safe — confirm this is how we wire it.
