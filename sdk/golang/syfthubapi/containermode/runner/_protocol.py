"""Container-runtime env-var protocol — single source of truth.

Keep in sync with sdk/golang/syfthubapi/containermode/executor.go.
A Go test (containermode/protocol_test.go) parses this file at build
time and fails the test suite if any Go constant drifts.

Imported by server.py (outside bwrap) and _syft_audit.py (inside bwrap,
where only stdlib is on sys.path). Do not add third-party imports.
"""
from typing import Final

# Host-set env vars read by server.py.
SYFT_HANDLER_ENV: Final[str]      = "_SYFT_HANDLER_ENV"
SYFT_ALLOW_SUBPROC: Final[str]    = "SYFT_ALLOW_SUBPROC"
SYFT_WORKSPACE_SCOPE: Final[str]  = "SYFT_WORKSPACE_SCOPE"
SYFT_SANDBOX_NET: Final[str]      = "SYFT_SANDBOX_NET"
SYFT_SUBPROC_ENV: Final[str]      = "SYFT_SUBPROC_ENV"

# server.py-set env vars read by the handler / _syft_audit.py inside bwrap.
SYFT_ALLOW_SUBPROCESS: Final[str] = "SYFT_ALLOW_SUBPROCESS"
SYFT_CODE_DIR: Final[str]         = "SYFT_CODE_DIR"
SYFT_WORKSPACE_DIR: Final[str]    = "SYFT_WORKSPACE_DIR"

# In-bwrap mount paths visible to the handler.
GUEST_CODE_DIR: Final[str]      = "/app/code"
GUEST_WORKSPACE_DIR: Final[str] = "/app/workspace"
