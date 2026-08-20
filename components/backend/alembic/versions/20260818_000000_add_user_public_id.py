"""Add users.public_id — a stable, opaque external user identifier.

``users.id`` is a sequential integer primary key. It must never become an
external, permanently-bound reference: doing so hands every relying party
SyftHub's internal id space (approximate user count, relative signup order) and
a shared join key with which two unrelated relying parties can correlate the
same person. The codebase already declines to expose it (see the privacy notes
on ``EndpointPublicResponse`` and ``PublicUserProfile``).

``public_id`` is that external reference instead — a random UUID, unique and
immutable, which will back the OIDC ``sub`` claim.

Migration shape, and why:

1. Add the column **nullable with no default**. That is a catalogue-only change
   on PostgreSQL: no table rewrite, so the ACCESS EXCLUSIVE lock is held only
   momentarily rather than for the length of a rewrite.
2. Backfill every existing row with a distinct value.
3. Add the unique index.
4. Constrain to NOT NULL and attach a ``gen_random_uuid()`` server default.

Step 4's server default is load-bearing, not decoration. ``deploy.sh``'s
``run_migrations()`` runs *before* ``deploy_services()`` and only brings up the
database — the **previous release keeps serving traffic throughout**. That code
has no ``public_id`` in its ORM model, so its signup INSERTs omit the column
entirely. Without a database-side default, every registration between this
migration committing and the new release rolling in would fail on a NOT NULL
violation. A Python-side default cannot cover that window, because it exists
only in the new code.

``gen_random_uuid()`` is built into PostgreSQL 13+ (deployments run
``postgres:16-alpine``). SQLite has no equivalent and cannot ``ALTER COLUMN``,
so there the column stays nullable; the ORM-side ``default=uuid.uuid4`` covers
inserts, and a freshly created dev database gets NOT NULL from ``create_all()``.

Revision ID: 022_user_public_id
Revises: 021_drop_user_heartbeat_fields
Create Date: 2026-08-18 00:00:00.000000+00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022_user_public_id"
down_revision: str | None = "021_drop_user_heartbeat_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_users = sa.table(
    "users",
    sa.column("id", sa.Integer),
    sa.column("public_id", sa.Uuid()),
)


def _backfill_public_ids(bind: sa.engine.Connection) -> None:
    """Assign a distinct UUID to every row that lacks one, from Python.

    Used on dialects without a UUID-generating SQL function. Runs inside the
    migration transaction, so it is atomic with the schema change.
    """
    rows = bind.execute(
        sa.select(_users.c.id).where(_users.c.public_id.is_(None))
    ).fetchall()
    for (user_id,) in rows:
        bind.execute(
            _users.update().where(_users.c.id == user_id).values(public_id=uuid.uuid4())
        )


def upgrade() -> None:
    """Add, backfill, and constrain users.public_id."""
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    # 1. Nullable, no default — catalogue-only on PostgreSQL, no rewrite.
    op.add_column("users", sa.Column("public_id", sa.Uuid(), nullable=True))

    # 2. Backfill. One statement on PostgreSQL; gen_random_uuid() is volatile,
    #    so each row receives a distinct value.
    if is_postgresql:
        op.execute(
            sa.text(
                "UPDATE users SET public_id = gen_random_uuid() WHERE public_id IS NULL"
            )
        )
    else:
        _backfill_public_ids(bind)

    # 3. Uniqueness.
    op.create_index("idx_users_public_id", "users", ["public_id"], unique=True)

    # 4. Constrain, and hand the still-running previous release a default it
    #    can rely on. SQLite supports neither statement.
    if is_postgresql:
        op.alter_column(
            "users",
            "public_id",
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        )


def downgrade() -> None:
    """Drop users.public_id.

    Irreversible in effect: any relying party that has bound accounts to these
    values loses them, and re-running the upgrade mints different UUIDs.
    """
    op.drop_index("idx_users_public_id", table_name="users")
    op.drop_column("users", "public_id")
