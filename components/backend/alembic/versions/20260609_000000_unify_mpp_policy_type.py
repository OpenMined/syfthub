"""Unify the pay-as-you-go (MPP) billing policy type to ``mpp``.

Historically the same per-request, Hub-wallet-settled billing policy was stored
under four interchangeable ``type`` strings — ``mpp``, ``mpp_accounting``,
``accounting`` and ``transaction`` — which forced every reader (backend
classifier, frontend cards, chat cost estimator) to keep matching sets in sync
and caused inconsistent paid/free state across the UI.

``mpp`` is the canonical spelling because that is exactly what syft-space (the
publisher) writes: its publish handler overrides the policy type with the wallet
provider (``mpp`` / ``xendit``). This migration rewrites the legacy spellings
(``mpp_accounting`` / ``accounting`` / ``transaction``) to ``mpp`` across every
endpoint's ``policies`` JSON, including policies nested inside composite wrappers
(``all_of`` / ``any_of`` / ``access_group`` / ``not``) under ``config['policies']``.
Prepaid providers (``xendit`` / ``stripe``) are left untouched.

Downgrade is a no-op: once collapsed, the original ``mpp_accounting`` vs
``accounting`` vs ``transaction`` spelling cannot be recovered (mirrors the
accounting-password encryption migration's one-way nature).

Revision ID: 020_unify_mpp_policy_type
Revises: 019_add_user_last_login_at
Create Date: 2026-06-09 00:00:00.000000+00:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "020_unify_mpp_policy_type"
down_revision: str | None = "019_add_user_last_login_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Legacy spellings of the pay-as-you-go (MPP) policy type, collapsed into one.
_LEGACY_MPP_TYPES = {"mpp_accounting", "accounting", "transaction"}
_CANONICAL_MPP_TYPE = "mpp"


def _rewrite_policy(policy: Any) -> bool:
    """Rewrite a legacy MPP ``type`` to the canonical one, recursing into any
    composite children under ``config['policies']``. Returns whether anything
    changed."""
    if not isinstance(policy, dict):
        return False
    changed = False
    ptype = policy.get("type")
    if isinstance(ptype, str) and ptype.lower() in _LEGACY_MPP_TYPES:
        policy["type"] = _CANONICAL_MPP_TYPE
        changed = True
    config = policy.get("config")
    if isinstance(config, dict):
        children = config.get("policies")
        if isinstance(children, list):
            for child in children:
                if _rewrite_policy(child):
                    changed = True
    return changed


def upgrade() -> None:
    connection = op.get_bind()
    endpoints = sa.table(
        "endpoints",
        sa.column("id", sa.Integer),
        sa.column("policies", sa.JSON),
    )

    rows = connection.execute(
        sa.select(endpoints.c.id, endpoints.c.policies)
    ).fetchall()

    for endpoint_id, policies in rows:
        if not isinstance(policies, list) or not policies:
            continue
        changed = False
        for policy in policies:
            if _rewrite_policy(policy):
                changed = True
        if changed:
            connection.execute(
                endpoints.update()
                .where(endpoints.c.id == endpoint_id)
                .values(policies=policies)
            )


def downgrade() -> None:
    # One-way: the original mpp_accounting / accounting / transaction spelling
    # is not recoverable once collapsed into mpp.
    pass
