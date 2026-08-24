"""Add the satellites table and endpoints.space_id.

``users.domain`` is one nullable string, so an account can describe exactly one
host — and four writers updated it (profile edit, publish, sync, health report),
so two spaces under one account overwrote each other's origin on every heartbeat.
Whichever reported last decided where all of that account's endpoints appeared
to live. Per-satellite rows end that by construction.

``id`` is internal; ``public_id`` is the opaque UUID that crosses API boundaries
and will fill a satellite token's ``aud``. Separating them makes the exposed
identifier rotatable without touching a foreign key — a uuid primary key could
not offer that.

Backfill: one ``kind='space'`` satellite per user with a domain, and their
endpoints pointed at it. Users without a domain get no row; inventing an empty
satellite would make "does this account own any satellites yet" answer wrongly.
``slug`` comes from the username — unique per user, recognisable to the owner.
Domains are copied verbatim: normalising here would disagree with the previous
release, which is still writing them unnormalised. The app normalises on the
next heartbeat instead.

Deploy window: ``deploy.sh`` migrates before rolling services, so the previous
release serves traffic throughout. It knows nothing of these tables and keeps
writing ``users.domain``, which this migration leaves alone. ``users.domain`` is
dropped in a later release, once no running code writes it.

Revision ID: 025_satellites
Revises: 024_collective_station_url
Create Date: 2026-08-24 00:00:00.000000+00:00
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "025_satellites"
down_revision: str | None = "024_collective_station_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Matches domain.base_url.MAX_BASE_URL_LENGTH and users.domain's width.
_BASE_URL_LENGTH = 500

_satellites = sa.table(
    "satellites",
    sa.column("id", sa.Integer),
    sa.column("public_id", sa.Uuid()),
    sa.column("user_id", sa.Integer),
    sa.column("kind", sa.String),
    sa.column("slug", sa.String),
    sa.column("base_url", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

_users = sa.table(
    "users",
    sa.column("id", sa.Integer),
    sa.column("username", sa.String),
    sa.column("domain", sa.String),
)


def _users_with_domains(bind: sa.engine.Connection) -> Sequence[sa.Row]:
    """Every user carrying a domain, in id order."""
    return bind.execute(
        sa.select(_users.c.id, _users.c.username, _users.c.domain)
        .where(_users.c.domain.isnot(None))
        .where(_users.c.domain != "")
        .order_by(_users.c.id)
    ).fetchall()


def upgrade() -> None:
    """Create satellites, add endpoints.space_id, and backfill both."""
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    op.create_table(
        "satellites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=_BASE_URL_LENGTH), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_satellites_public_id", "satellites", ["public_id"], unique=True
    )
    op.create_index("idx_satellites_user_id", "satellites", ["user_id"])
    op.create_index(
        "idx_satellites_user_slug", "satellites", ["user_id", "slug"], unique=True
    )
    op.create_index(
        "idx_satellites_user_base_url",
        "satellites",
        ["user_id", "base_url"],
        unique=True,
    )

    # Consistent with users.public_id; the previous release cannot insert here
    # anyway, having no such model.
    if is_postgresql:
        op.alter_column(
            "satellites",
            "public_id",
            server_default=sa.text("gen_random_uuid()"),
        )

    op.add_column("endpoints", sa.Column("space_id", sa.Integer(), nullable=True))

    # Batch mode: SQLite cannot ALTER in a constraint, so it copy-and-moves,
    # while PostgreSQL gets a plain ALTER. Scoped to the constraint alone so
    # SQLite rewrites endpoints once.
    #
    # SET NULL, not CASCADE: deleting a satellite orphans its endpoints rather
    # than destroying catalogue entries and the addresses buyers hold.
    with op.batch_alter_table("endpoints", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_endpoints_space_id_satellites",
            "satellites",
            ["space_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index("idx_endpoints_space_id", "endpoints", ["space_id"])

    _backfill(bind, is_postgresql)


def _backfill(bind: sa.engine.Connection, is_postgresql: bool) -> None:
    """Give every domain-carrying user one space, and point endpoints at it."""
    rows = _users_with_domains(bind)
    if not rows:
        return

    # Python, not func.now(): the columns are timezone-aware and SQLite's
    # CURRENT_TIMESTAMP is not.
    now = datetime.now(timezone.utc)
    for user_id, username, domain in rows:
        values = {
            "user_id": user_id,
            "kind": "space",
            "slug": username,
            # Verbatim — see module docstring.
            "base_url": domain,
            "created_at": now,
            "updated_at": now,
        }
        if not is_postgresql:
            # No gen_random_uuid() to fall back on, and the column is NOT NULL.
            values["public_id"] = uuid.uuid4()
        bind.execute(_satellites.insert().values(**values))

    # The correlated subquery matches at most one row: exactly one space exists
    # per user at this point.
    op.execute(
        sa.text(
            """
            UPDATE endpoints
               SET space_id = (
                   SELECT s.id FROM satellites s
                    WHERE s.user_id = endpoints.user_id
                      AND s.kind = 'space'
               )
             WHERE space_id IS NULL
               AND EXISTS (
                   SELECT 1 FROM satellites s
                    WHERE s.user_id = endpoints.user_id
                      AND s.kind = 'space'
               )
            """
        )
    )


def downgrade() -> None:
    """Drop endpoints.space_id and the satellites table.

    ``users.domain`` is untouched by the upgrade, so nothing is lost except
    satellites registered after it, whose origins were never mirrored back.
    """
    op.drop_index("idx_endpoints_space_id", table_name="endpoints")
    with op.batch_alter_table("endpoints", schema=None) as batch_op:
        batch_op.drop_constraint("fk_endpoints_space_id_satellites", type_="foreignkey")
    op.drop_column("endpoints", "space_id")

    op.drop_index("idx_satellites_user_base_url", table_name="satellites")
    op.drop_index("idx_satellites_user_slug", table_name="satellites")
    op.drop_index("idx_satellites_user_id", table_name="satellites")
    op.drop_index("idx_satellites_public_id", table_name="satellites")
    op.drop_table("satellites")
