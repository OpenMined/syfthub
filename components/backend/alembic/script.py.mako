"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# Revision identifiers, used by Alembic
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


# =============================================================================
# MIGRATION SAFETY REMINDERS
# =============================================================================
#
# For zero-downtime migrations on production PostgreSQL databases:
#
# 1. SET LOCK TIMEOUT: Add at the start of migration transactions:
#    op.execute("SET LOCAL lock_timeout = '3s'")
#
# 2. CREATE INDEXES CONCURRENTLY: Don't block writes during index creation.
#    Run outside a transaction:
#    with op.get_context().autocommit_block():
#        op.create_index(..., postgresql_concurrently=True)
#
# 3. ADD COLUMNS NULLABLE FIRST: Add as nullable, backfill, then add NOT NULL.
#    # Step 1: Add nullable column
#    op.add_column('table', sa.Column('col', sa.String(), nullable=True))
#    # Step 2: Backfill data (in separate migration if large table)
#    op.execute("UPDATE table SET col = 'default' WHERE col IS NULL")
#    # Step 3: Add NOT NULL constraint (after backfill is verified)
#    op.alter_column('table', 'col', nullable=False)
#
# 4. VALIDATE CONSTRAINTS SEPARATELY (PostgreSQL 18+):
#    op.execute("ALTER TABLE t ADD CONSTRAINT c CHECK (x > 0) NOT VALID")
#    # Then in a separate migration:
#    op.execute("ALTER TABLE t VALIDATE CONSTRAINT c")
#
# 5. AVOID TYPE CHANGES: ALTER COLUMN TYPE rewrites the entire table.
#    Use expand/contract pattern: add new column, migrate data, drop old.
#
# =============================================================================


def upgrade() -> None:
    """Apply migration changes."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Reverse migration changes."""
    ${downgrades if downgrades else "pass"}
