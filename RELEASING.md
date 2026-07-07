# Releasing SDKs

This document describes how to release the Python and TypeScript SDKs to their respective package registries (PyPI and npm).

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
- [Version Numbering](#version-numbering)
- [Troubleshooting](#troubleshooting)
- [Rollback Procedures](#rollback-procedures)

---

## Prerequisites

Before releasing, ensure you have:

- **Repository administrator access** - Required for environment and secrets configuration
- **PyPI account** - With ownership/maintainer access to the `syfthub-sdk` package
- **npm account** - With publish access to the `@syfthub` organization

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

---

## Version Numbering

Both SDKs follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features, backwards compatible
- **PATCH** (0.0.X): Bug fixes, backwards compatible

### Pre-release Versions

For pre-release testing, use these formats:

| Type | Python | TypeScript |
|------|--------|------------|
| Alpha | `0.2.0a1` | `0.2.0-alpha.1` |
| Beta | `0.2.0b1` | `0.2.0-beta.1` |
| Release Candidate | `0.2.0rc1` | `0.2.0-rc.1` |

Tag format for pre-releases:
- `python-sdk/v0.2.0a1`
- `typescript-sdk/v0.2.0-alpha.1`

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

---

## Future Enhancements

Consider implementing these improvements:

- [ ] **Release Please** - Automated version bumping and changelog generation
- [ ] **Changesets** - Alternative changelog and release management
- [ ] **Slack/Discord notifications** - Alert team on successful releases
- [ ] **Automated compatibility testing** - Test against live API before release
