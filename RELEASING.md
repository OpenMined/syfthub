# Releasing the Python SDK

How `syfthub-sdk` gets from `sdk/python` to PyPI. Releases are driven by a tag; the
`release-python-sdk.yml` workflow does the rest.

## One-time setup

- **PyPI trusted publisher.** On PyPI, under the `syfthub-sdk` project, add a publisher with
  owner `OpenMined`, repository `syfthub`, workflow `release-python-sdk.yml` and environment
  `pypi`. No long-lived token is stored anywhere.
- **GitHub environment `pypi`.** Repository settings, Environments, create `pypi`. Add required
  reviewers if releases should wait for approval.
- **Tag ruleset.** Repository settings, Rules, a ruleset for tags matching `python-sdk/v*` that
  restricts creation and deletion to maintainers.

## Release

1. Bump `version` in `sdk/python/pyproject.toml`. For a stable release also set the
   `Development Status` classifier to `5 - Production/Stable`.
2. Open a pull request, get it reviewed, merge to `main`.
3. Tag the merge commit and push the tag:

   ```bash
   git checkout main && git pull
   git tag python-sdk/v2.0.0
   git push origin python-sdk/v2.0.0
   ```

4. Watch "Release Python SDK" under Actions. It checks that the tag matches the version in
   `pyproject.toml`, runs ruff, mypy and the unit tests, builds the wheel and sdist, publishes
   to PyPI and creates a GitHub Release.
5. Verify on https://pypi.org/project/syfthub-sdk/ and with a fresh install.

## Version numbers

[Semantic Versioning](https://semver.org/). Pre-releases use PEP 440 suffixes, `2.0.0a1`,
`2.0.0b1`, `2.0.0rc1`, and the tag carries the same string: `python-sdk/v2.0.0a1`. `pip`
installs a pre-release only with `--pre` or an explicit pin. Mark the GitHub Release as a
pre-release by hand; the workflow does not do it.

## When something goes wrong

- **Version mismatch.** The workflow stops when the tag and `pyproject.toml` disagree. Fix the
  version, merge, delete the tag on the remote and tag again.
- **Lint or tests fail.** Nothing is published. Fix on `main`, then move the tag.
- **A bad release is out.** PyPI does not allow unpublishing. Yank the version on PyPI so new
  installs skip it, then release a patch.

## Retired packages

`@syfthub/sdk` on npm and the Go module are no longer released. The TypeScript client lives in
`components/frontend/src/lib/sdk` and ships inside the frontend image; the last published versions and
the Go SDK are kept on the `legacy-sdks` branch.
