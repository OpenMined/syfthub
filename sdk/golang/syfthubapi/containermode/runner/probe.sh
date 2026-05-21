#!/bin/sh
# probe.sh — verification probe run against any image that wants to be used
# as a syfthub endpoint runner. Exits 0 only when the image is bwrap-capable
# AND ships the syft_runtime files at /usr/local/lib/syft_runtime/.
#
# Caller (Go side): runs this inside a one-shot container with the same
# hardening flags the real endpoint container uses (read-only FS, cap-drop
# ALL, no-new-privileges, user 1000:1000) so we test what we deploy.
#
# Exit codes:
#   0   — verified
#   10  — bwrap not on PATH
#   11  — bwrap rejected the basic --unshare-* flags (no user-NS support)
#   12  — syft_runtime missing or unimportable
#   13  — python3 too old (< 3.9)
set -eu

# 1. bwrap on PATH and executable.
if ! command -v bwrap >/dev/null 2>&1; then
    echo "probe: bwrap not found on PATH" >&2
    exit 10
fi
if [ ! -x "$(command -v bwrap)" ]; then
    echo "probe: bwrap not executable" >&2
    exit 10
fi

# 2. bwrap can actually do its thing on THIS host kernel. Tests the
# same flag set the runtime uses. We DON'T pass --unshare-pid here
# because mounting a fresh procfs from a userns that owns the pidns
# but not the netns is rejected by Linux ≥ 4.18; the runtime works
# around it by binding the container's /proc instead of mounting a
# fresh one. The probe just needs to confirm bwrap can create the
# userns + ipc/uts namespaces and set up its mount tree.
if ! bwrap --ro-bind / / \
           --unshare-user --unshare-ipc --unshare-uts \
           --ro-bind /proc /proc /bin/true >/dev/null 2>&1; then
    echo "probe: bwrap could not create namespaces; check kernel.unprivileged_userns_clone" >&2
    exit 11
fi

# 3. syft_runtime files present + importable. _syft_audit registers the
# audit hook on import (side-effect); syft_entry + session_loop are the
# in-bwrap loader and AgentSession.
if ! bwrap --ro-bind / / \
           --tmpfs /tmp \
           --ro-bind /proc /proc \
           --setenv PYTHONPATH /usr/local/lib/syft_runtime \
           python3 -c 'import _syft_audit, syft_entry, session_loop' \
           >/dev/null 2>&1; then
    echo "probe: /usr/local/lib/syft_runtime missing or broken" >&2
    exit 12
fi

# 4. Python ≥ 3.9 (sys.addaudithook + os.fspath() everywhere).
if ! python3 -c 'import sys; assert sys.version_info >= (3, 9), sys.version' \
        >/dev/null 2>&1; then
    echo "probe: python3 too old (<3.9)" >&2
    exit 13
fi

echo "probe: bwrap verified"
