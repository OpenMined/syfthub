# Releasing SDKs and Desktop App

This document describes how to release the Python and TypeScript SDKs to their respective package registries (PyPI and npm), and how to publish the SyftHub Desktop app to GitHub Releases.

## Table of Contents

- [Prerequisites](#prerequisites)
- [One-Time Setup](#one-time-setup)
  - [PyPI Trusted Publisher](#pypi-trusted-publisher)
  - [npm Trusted Publisher](#npm-trusted-publisher)
  - [GitHub Environments](#github-environments)
  - [Tag Protection Rules](#tag-protection-rules)
- [Release Process](#release-process)
  - [Python SDK](#python-sdk)
  - [TypeScript SDK](#typescript-sdk)
  - [SyftHub Desktop](#syfthub-desktop)
- [Version Numbering](#version-numbering)
- [Troubleshooting](#troubleshooting)
- [Rollback Procedures](#rollback-procedures)

---

## Prerequisites

Before releasing, ensure you have:

- **Repository administrator access** - Required for environment and secrets configuration
- **PyPI account** - With ownership/maintainer access to the `syfthub-sdk` package
- **npm account** - With publish access to the `@syfthub` organization
- **Permission to push `desktop/v*` tags** - Required to trigger desktop releases (no external registry account needed; artifacts are published to GitHub Releases)

---

## One-Time Setup

These steps only need to be performed once when setting up the repository.

### PyPI Trusted Publisher

PyPI supports OpenID Connect (OIDC) for secure, tokenless authentication from GitHub Actions.

1. **Log in to PyPI** at https://pypi.org

2. **Navigate to your project settings:**
   - Go to "Your projects" → `syfthub-sdk` → "Manage" → "Publishing"

3. **Add a new trusted publisher** with these settings:

   | Field | Value |
   |-------|-------|
   | Owner | `OpenMined` (or your organization) |
   | Repository | `<repository-name>` |
   | Workflow name | `release-python-sdk.yml` |
   | Environment name | `pypi` (optional, but recommended) |

4. **Save the configuration**

> **Note:** If the package doesn't exist on PyPI yet, you can configure trusted publishing as a "pending publisher" before the first release.

### npm Trusted Publisher

npm supports OpenID Connect (OIDC) for secure, tokenless authentication from GitHub Actions (similar to PyPI).

> **Note:** Unlike PyPI, npm requires the package to exist before configuring trusted publishing. For the first release of a new package, see [First-Time npm Publish](#first-time-npm-publish) below.

#### For Existing Packages

1. **Log in to npm** at https://www.npmjs.com

2. **Navigate to your package settings:**
   - Go to your package → "Settings" → "Trusted Publishers"

3. **Add a new trusted publisher** with these settings:

   | Field | Value |
   |-------|-------|
   | Owner | `OpenMined` |
   | Repository | `syfthub` |
   | Workflow name | `release-typescript-sdk.yml` |
   | Environment name | `npm` (optional, but recommended) |

4. **Save the configuration**

#### First-Time npm Publish

For a brand new package that doesn't exist on npm yet:

1. **Option A: Manual first publish**
   - Generate a temporary automation token on npm
   - Manually run `npm publish --access public` locally
   - Then configure trusted publishing as above
   - Delete the automation token

2. **Option B: Use placeholder tool**
   - Use [setup-npm-trusted-publish](https://github.com/azu/setup-npm-trusted-publish) to create a minimal placeholder package
   - Then configure trusted publishing

> **Security Benefit:** OIDC trusted publishing eliminates long-lived tokens, provides automatic provenance attestations, and each publish uses short-lived, workflow-specific credentials.

### GitHub Environments

GitHub Environments provide additional security controls for deployments.

1. **Navigate to environment settings:**
   - Repository → "Settings" → "Environments"

2. **Create `pypi` environment:**
   - Click "New environment"
   - Name: `pypi`
   - Configure protection rules (optional):
     - Required reviewers: Add 1+ maintainers
     - Deployment branches: Select "main" only

3. **Create `npm` environment:**
   - Click "New environment"
   - Name: `npm`
   - Configure same protection rules as above

> **Tip:** Environment protection rules require manual approval before releases, adding an extra layer of safety.

### Tag Protection Rules

Prevent unauthorized tag creation for releases.

1. **Navigate to tag rules:**
   - Repository → "Settings" → "Rules" → "Rulesets"

2. **Create a new ruleset** for release tags:
   - Name: `SDK Release Tags`
   - Enforcement: Active
   - Target: Tags matching patterns:
     - `python-sdk/v*`
     - `typescript-sdk/v*`
     - `desktop/v*`
   - Rules:
     - Restrict creations: Only maintainers
     - Restrict deletions: Only maintainers

---

## Release Process

### Python SDK

#### Release Checklist

```
[ ] 1. Update version in sdk/python/pyproject.toml
[ ] 2. Update sdk/python/CHANGELOG.md
[ ] 3. Create PR and get approval
[ ] 4. Merge PR to main
[ ] 5. Create and push tag
[ ] 6. Verify workflow succeeds
[ ] 7. Verify package on PyPI
```

#### Step-by-Step

1. **Update the version** in `sdk/python/pyproject.toml`:

   ```toml
   [project]
   name = "syfthub-sdk"
   version = "0.2.0"  # Update this
   ```

2. **Update the changelog** in `sdk/python/CHANGELOG.md`

3. **Create a pull request** with these changes and get approval

4. **Merge to main** after approval

5. **Create and push the release tag:**

   ```bash
   git checkout main
   git pull origin main
   git tag python-sdk/v0.2.0
   git push origin python-sdk/v0.2.0
   ```

6. **Monitor the workflow:**
   - Go to "Actions" → "Release Python SDK"
   - Verify all steps complete successfully

7. **Verify the release:**
   - Check https://pypi.org/project/syfthub-sdk/
   - Check GitHub Releases page

### TypeScript SDK

#### Release Checklist

```
[ ] 1. Update version in sdk/typescript/package.json
[ ] 2. Update sdk/typescript/CHANGELOG.md
[ ] 3. Create PR and get approval
[ ] 4. Merge PR to main
[ ] 5. Create and push tag
[ ] 6. Verify workflow succeeds
[ ] 7. Verify package on npm
```

#### Step-by-Step

1. **Update the version** in `sdk/typescript/package.json`:

   ```json
   {
     "name": "@syfthub/sdk",
     "version": "0.2.0"
   }
   ```

2. **Update the changelog** in `sdk/typescript/CHANGELOG.md`

3. **Create a pull request** with these changes and get approval

4. **Merge to main** after approval

5. **Create and push the release tag:**

   ```bash
   git checkout main
   git pull origin main
   git tag typescript-sdk/v0.2.0
   git push origin typescript-sdk/v0.2.0
   ```

6. **Monitor the workflow:**
   - Go to "Actions" → "Release TypeScript SDK"
   - Verify all steps complete successfully

7. **Verify the release:**
   - Check https://www.npmjs.com/package/@syfthub/sdk
   - Check GitHub Releases page

### SyftHub Desktop

The desktop app is a Wails (Go + React) application that ships as platform-native binaries via GitHub Releases. It does **not** publish to any external package registry, so no trusted-publisher setup is required.

#### What the pipeline does

Workflow: `.github/workflows/release-desktop.yml`

Triggered by pushing any tag matching `desktop/v*`. Concurrency-guarded by `release-desktop` so two releases can't race. Five jobs:

1. **`prepare`** (`ubuntu-latest`) — strips `desktop/v` off the tag, validates it as semver (`X.Y.Z` or `X.Y.Z-pre.N`), and emits `version` / `version_tag` outputs.
2. **`build-linux`** (`ubuntu-latest`) — Node LTS + Go 1.23 + Wails v2.11.0. Installs `libgtk-3-dev` / `libwebkit2gtk-4.1-dev`, runs `wails build -platform linux/amd64 -tags webkit2_41 -ldflags "-X 'main.Version=$VERSION'"`. Produces `syfthub-desktop-linux-amd64` + `.sha256`.
3. **`build-windows`** (`windows-latest`) — same toolchain, `wails build -platform windows/amd64`. Produces `syfthub-desktop-windows-amd64.exe` + `.sha256`.
4. **`build-macos-arm64`** (`macos-14`) — `wails build -platform darwin/arm64`, then `zip -r` the `.app` bundle. Produces `syfthub-desktop-macos-arm64.zip` + `.sha256`.
5. **`release`** (`ubuntu-latest`) — downloads all artifacts, concatenates the per-file checksums into `checksums.txt`, then uses `softprops/action-gh-release@v2` to create/update the GitHub Release at `desktop/v<VERSION>` with a templated body (download table, install instructions, checksum verification). `generate_release_notes: true` auto-appends commit notes.

The `WAILS_VERSION` env var (currently `v2.11.0`) is pinned at the top of the workflow — bump it there if you need a newer Wails toolchain.

#### Release Checklist

```
[ ] 1. Verify the desktop app builds locally (wails build)
[ ] 2. Decide the version (see Version Numbering below)
[ ] 3. Update CHANGELOG / release notes if maintained
[ ] 4. Ensure desktop-app is merged into main (or chosen release branch)
[ ] 5. Create and push the desktop/vX.Y.Z tag
[ ] 6. Monitor the release-desktop workflow
[ ] 7. Verify the GitHub Release and download/checksums
```

#### Step-by-Step

1. **Verify a local build** (optional but recommended):

   ```bash
   cd syfthub-desktop
   wails build
   ```

   The version baked into the binary comes from the `-X 'main.Version=$VERSION'` ldflag set in CI from the tag; you don't need to edit any version file in the repo.

2. **Create and push the release tag** from the commit you want to ship:

   ```bash
   git checkout main         # or the release branch
   git pull origin main
   git tag desktop/v0.1.1
   git push origin desktop/v0.1.1
   ```

3. **Monitor the workflow:**
   - Go to "Actions" → "Release SyftHub Desktop"
   - Verify `prepare`, all three `build-*` jobs, and `release` complete successfully

4. **Verify the release:**
   - Check the GitHub Releases page for `SyftHub Desktop v<X.Y.Z>`
   - Confirm all six asset files are present (3 binaries + 3 `.sha256` files) plus `checksums.txt`
   - Download one binary and verify its SHA-256 matches `checksums.txt`

#### Platform Coverage

| Platform | Architecture | Artifact |
|----------|--------------|----------|
| Linux | x86_64 | `syfthub-desktop-linux-amd64` (raw ELF binary) |
| Windows | x86_64 | `syfthub-desktop-windows-amd64.exe` |
| macOS | Apple Silicon (M1/M2/M3) | `syfthub-desktop-macos-arm64.zip` (zipped `.app` bundle) |

> **Not currently built:** macOS Intel (`darwin/amd64`), Linux arm64, Windows arm64. Add a job to `release-desktop.yml` if needed.

#### Known Gaps

- **No code signing or notarization.** macOS users must right-click → Open to bypass Gatekeeper on first launch. Windows SmartScreen will warn on the unsigned `.exe`.
- **No DMG installer for macOS** — only a zipped `.app`.
- **No MSI/installer for Windows** — only a raw `.exe`.

#### Auto-update manifest (Phase 1)

The release workflow publishes an `update manifest` at a stable URL that
the desktop app polls to discover new releases and enforce a minimum
supported version. See `docs/architecture/auto-update-plan.md` for the
full design.

- Source files in `syfthub-desktop/`:
  - `.min-supported-version` — single-line semver. Bumped only for
    security or data-corruption fixes. Clients running below this value
    enter the hard-gate state and must update before they can continue.
  - `.must-update-reason` — optional short string shown to users in the
    must-update modal. Leave empty for non-security releases.
- Manifest is published to a non-versioned GitHub Release tagged
  `desktop/latest-stable`. The release is bootstrapped automatically on
  the first run of the `manifest` job; thereafter the workflow uploads
  `manifest.json` with `--clobber`.
- Pre-release tags (`desktop/v0.2.0-beta.1` etc.) intentionally do **not**
  advance the stable manifest. They publish binaries but the
  `latest-stable` pointer stays where it is.
- Manifest URL (do not change without a coordinated client release):
  `https://github.com/OpenMined/syfthub/releases/download/desktop/latest-stable/manifest.json`

**Bumping `min_supported_version`:**

1. Determine the lowest version that contains the security fix.
2. Edit `syfthub-desktop/.min-supported-version` in the release PR.
3. Optionally populate `syfthub-desktop/.must-update-reason` with a one-line
   summary (`security: CVE-2026-XXXX` style).
4. Cut the release tag as usual. The `manifest` job picks up the new floor.

**Emergency rollback:** if a release advances the floor incorrectly,
either (a) overwrite the manifest by editing `.min-supported-version` and
cutting a patch release, or (b) manually replace the `manifest.json`
asset under `desktop/latest-stable` via `gh release upload --clobber`.

**Emergency bypass on a single client:**

```bash
# Disables the entire updater (no checks, no banner, no hard-gate)
SYFTHUB_DESKTOP_SKIP_UPDATE_CHECK=1 ./syfthub-desktop
```

**Tag protection rule:** the existing rule covers `desktop/v*`. Add a
second rule restricting creation/deletion of `desktop/latest-stable` to
maintainers.

#### macOS code signing + notarization (Phase 4 — currently inactive)

The `build-macos-arm64` job has scaffolding for `codesign` and
`xcrun notarytool` that activates automatically when the required
secrets are present. While they are absent (today), macOS continues to
ship unsigned and the desktop app's in-app updater falls back to the
Phase 2 manual install flow (download + reveal in Finder).

Required GitHub secrets to enable:

| Secret | What it is |
|---|---|
| `APPLE_DEVELOPER_ID_CERT_P12_BASE64` | Base64 of the `.p12` containing your "Developer ID Application" cert + private key. Generate with `base64 -i cert.p12 -o cert.p12.b64`. |
| `APPLE_DEVELOPER_ID_CERT_PASSWORD` | Password used when exporting the `.p12`. |
| `APPLE_DEVELOPER_ID_IDENTITY` | The codesign identity string, e.g. `Developer ID Application: OpenMined (TEAMID1234)`. Get it from `security find-identity -v -p codesigning`. |
| `APPLE_NOTARIZATION_APPLE_ID` | The Apple ID email used to submit. |
| `APPLE_NOTARIZATION_TEAM_ID` | 10-character Team ID. |
| `APPLE_NOTARIZATION_APP_PASSWORD` | App-specific password generated at appleid.apple.com (NOT your Apple ID password). |

The workflow checks all three groups separately, so partial activation
is allowed: setting only the cert + identity will sign but not
notarize, which is enough to stop Gatekeeper warnings on installs from
trusted distribution channels.

Once all secrets are in place and the next stable release notarizes
successfully, flip `inPlaceSupported` to `true` in
`syfthub-desktop/internal/updater/install_darwin.go` and implement
`swapAndRelaunch` per the design notes in that file.

#### Manifest signing (Phase 5)

The desktop app's auto-updater verifies the manifest with an Ed25519
public key embedded in the binary. Until a real keypair is provisioned,
the repo ships a placeholder PEM and clients skip signature verification
("lenient" mode, default).

**One-time setup:**

1. Generate a fresh keypair:

   ```bash
   cd syfthub-desktop
   go run ./cmd/genkey
   ```

   The tool prints both PEMs on stdout. **Do not commit the private key.**

2. Replace the placeholder public key:

   - Open `syfthub-desktop/internal/updater/embed/manifest_pubkey.pem`.
   - Paste the entire `-----BEGIN PUBLIC KEY-----` block in place of
     the placeholder marker.

3. Add the private key as a GitHub secret named
   `DESKTOP_MANIFEST_SIGNING_KEY` (paste the entire
   `-----BEGIN PRIVATE KEY-----` block).

4. Commit and merge the public-key change. **Do not ship the next
   release yet** — give existing users a chance to upgrade to a client
   that has the public key embedded.

5. After at least one stable release with the embedded public key,
   start signing: the `manifest` job will automatically pick up the
   secret and produce `manifest.json.sig` alongside `manifest.json`.

**Rotating the key:**

Rotation requires shipping a new client release with the rotated
public key. Steps:

1. Generate a new keypair via `go run ./cmd/genkey`.
2. Replace the embedded public key in the repo.
3. Update the GitHub secret with the new private key.
4. Cut a new desktop release. Older clients (with the old public key)
   will fail to verify after the rotation; they fall back to lenient
   mode if the old key was already in lenient circulation, or refuse
   updates in strict mode.

**Strict mode** for security-conscious users / corporate deployments:

```bash
SYFTHUB_DESKTOP_REQUIRE_SIGNATURE=1 ./syfthub-desktop
```

In strict mode, unsigned manifests are refused — the client will enter
an offline state until a signed manifest is published.

---

## Version Numbering

All artifacts follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features, backwards compatible
- **PATCH** (0.0.X): Bug fixes, backwards compatible

### Pre-release Versions

For pre-release testing, use these formats:

| Type | Python | TypeScript | Desktop |
|------|--------|------------|---------|
| Alpha | `0.2.0a1` | `0.2.0-alpha.1` | `0.2.0-alpha.1` |
| Beta | `0.2.0b1` | `0.2.0-beta.1` | `0.2.0-beta.1` |
| Release Candidate | `0.2.0rc1` | `0.2.0-rc.1` | `0.2.0-rc.1` |

Tag format for pre-releases:
- `python-sdk/v0.2.0a1`
- `typescript-sdk/v0.2.0-alpha.1`
- `desktop/v0.2.0-beta.1`

> **Desktop note:** The `prepare` job validates the tag against `^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$`, so `0.2.0-beta.1` and `0.2.0-rc.1` pass while PyPI-style `0.2.0a1` does not. Stick to the TypeScript/SemVer-style pre-release suffix for desktop tags.

---

## Troubleshooting

### Version Mismatch Error

**Error:** `Version mismatch! Tag version (X.X.X) does not match pyproject.toml/package.json version (Y.Y.Y)`

**Solution:** Ensure the version in your package configuration file exactly matches the tag version:
- Tag `python-sdk/v0.2.0` requires `version = "0.2.0"` in pyproject.toml
- Tag `typescript-sdk/v0.2.0` requires `"version": "0.2.0"` in package.json

### PyPI Authentication Failed

**Error:** `403 Forbidden` or OIDC token error

**Solutions:**
1. Verify trusted publisher is configured correctly on PyPI
2. Check that the workflow filename matches exactly: `release-python-sdk.yml`
3. Ensure the environment name matches (if using environments)
4. Verify the repository owner/name match the PyPI configuration

### npm Authentication Failed

**Error:** `npm ERR! code ENEEDAUTH` or `403 Forbidden`

**Solutions:**
1. Verify trusted publisher is configured correctly on npmjs.com
2. Check that the workflow filename matches exactly: `release-typescript-sdk.yml`
3. Ensure the environment name matches (if using environments)
4. Verify the repository owner/name match the npm configuration (case-sensitive!)
5. Check that `repository.url` in package.json matches the GitHub repository URL

### npm Scope Not Found

**Error:** `npm ERR! 404 '@syfthub/sdk' is not in this registry`

**Solutions:**
1. Ensure `@syfthub` organization exists on npm
2. Verify you have publish access to the organization
3. For first publish, the organization admin may need to grant permissions

### Tests Failing

**Solution:** Fix the failing tests before releasing. The workflow intentionally blocks releases when tests fail to prevent publishing broken code.

### Build Artifacts Missing

**Error:** `No wheel file found` or `Expected file dist/index.js not found`

**Solutions:**
1. Run the build locally to verify it works: `uv build` or `npm run build`
2. Check for build errors in the workflow logs
3. Ensure all dependencies are correctly specified

### Desktop: Invalid Version Format

**Error:** `Invalid version format: <tag>` from the `prepare` job

**Solution:** The desktop pipeline accepts only SemVer-style versions. Use `desktop/vX.Y.Z` or `desktop/vX.Y.Z-pre.N` (e.g., `desktop/v0.2.0-beta.1`). PyPI-style suffixes like `0.2.0a1` are rejected.

### Desktop: No .app Bundle Found (macOS job)

**Error:** `::error::No .app bundle found` during the `build-macos-arm64` job

**Solution:** Wails normally outputs `syfthub-desktop.app` or `SyftHub Desktop.app` under `build/bin/`. If the output name has changed (e.g., via `wails.json`), update the lookup branches in `build-macos-arm64` → "Prepare artifacts" or rely on the fallback `find . -name "*.app"` path.

### Desktop: Wails Build Fails on Linux

**Error:** Build fails with missing GTK/WebKit headers

**Solution:** The workflow installs `libgtk-3-dev` and `libwebkit2gtk-4.1-dev`, and builds with `-tags webkit2_41`. If you bump Wails or the runner image and the WebKit ABI changes, update both the apt packages and the build tag together.

---

## Rollback Procedures

### PyPI

PyPI does not allow unpublishing packages (to prevent dependency confusion attacks). Instead:

1. **Yank the release** (hides from default installation):
   - Go to PyPI → Your project → Releases → Select version → "Yank"
   - Users with pinned versions can still install, but `pip install syfthub-sdk` won't get the yanked version

2. **Publish a new patch version** with the fix:
   - Increment the patch version (e.g., 0.2.0 → 0.2.1)
   - Include the fix and release normally

### npm

npm allows unpublishing within 72 hours:

1. **Unpublish** (within 72 hours):
   ```bash
   npm unpublish @syfthub/sdk@0.2.0
   ```

2. **After 72 hours**, deprecate instead:
   ```bash
   npm deprecate @syfthub/sdk@0.2.0 "This version has a critical bug, please upgrade to 0.2.1"
   ```

3. **Publish a new patch version** with the fix.

### SyftHub Desktop (GitHub Releases)

GitHub Releases can be edited or deleted, but binaries that users have already downloaded cannot be recalled.

1. **Mark the release as a pre-release or draft** to hide it from the "Latest" badge:
   - GitHub → Releases → Edit release → toggle "Set as a pre-release" (or "Save as draft" to fully unlist).

2. **Delete the release and tag** (only safe immediately after publish, before users have downloaded):
   ```bash
   gh release delete desktop/v0.2.0 --yes
   git push --delete origin desktop/v0.2.0
   git tag -d desktop/v0.2.0
   ```

3. **Publish a new patch version** with the fix:
   ```bash
   git tag desktop/v0.2.1
   git push origin desktop/v0.2.1
   ```

4. **Update release notes** of the bad release to point users at the fixed version.

> **Note:** There is no auto-update channel today, so users on the bad version must manually download the fix.

---

## Future Enhancements

Consider implementing these improvements:

- [ ] **Release Please** - Automated version bumping and changelog generation
- [ ] **Changesets** - Alternative changelog and release management
- [ ] **Slack/Discord notifications** - Alert team on successful releases
- [ ] **Automated compatibility testing** - Test against live API before release
- [ ] **Desktop: code signing + notarization** (Apple Developer ID, Windows Authenticode) so installers don't trip Gatekeeper / SmartScreen
- [ ] **Desktop: macOS Intel + Linux arm64 + Windows arm64 builds**
- [ ] **Desktop: DMG installer for macOS, MSI installer for Windows**
- [ ] **Desktop: in-app auto-updater** (e.g., via a manifest file in the release)
