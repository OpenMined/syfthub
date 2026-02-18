# Database Migrations

This directory contains Alembic database migrations for SyftHub.

## Quick Reference

```bash
# From components/backend directory:

# Check current migration status
uv run alembic current

# Run all pending migrations
uv run alembic upgrade head

# Generate a new migration (auto-detect changes from models)
uv run alembic revision --autogenerate -m "description of changes"

# Create an empty migration for manual SQL
uv run alembic revision -m "description of changes"

# Downgrade one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history

# View SQL without executing (offline mode)
uv run alembic upgrade head --sql
```

## For Existing Databases

If you have an existing database created before migrations were introduced (using `Base.metadata.create_all()`), you need to mark the initial migration as applied:

```bash
# Mark the initial migration as applied WITHOUT running it
uv run alembic stamp 001_initial
```

This tells Alembic that the current schema is at the `001_initial` revision, so future migrations will apply correctly.

## For New Databases

New databases will have migrations applied automatically:
- **Docker deployments**: The `entrypoint.sh` script runs `alembic upgrade head` on startup
- **Local development**: Run `uv run alembic upgrade head` after setting up

## Creating New Migrations

### Auto-generated migrations (recommended for model changes)

When you modify SQLAlchemy models, generate a migration that detects the changes:

```bash
uv run alembic revision --autogenerate -m "add user preferences table"
```

**Always review the generated migration!** Auto-generation can miss or misinterpret:
- Column type changes (especially between JSON and JSONB)
- Index changes on existing columns
- Data migrations (you must add these manually)

### Manual migrations (for data migrations or complex DDL)

For migrations that involve data transformation or complex schema changes:

```bash
uv run alembic revision -m "migrate user roles to new format"
```

Then edit the generated file to add your `upgrade()` and `downgrade()` logic.

## Migration Safety Guidelines

### For Production (PostgreSQL)

1. **Set lock timeout** to prevent blocking other queries:
   ```python
   op.execute("SET LOCAL lock_timeout = '3s'")
   ```

2. **Create indexes concurrently** (outside transaction):
   ```python
   with op.get_context().autocommit_block():
       op.create_index(
           "idx_users_new_column",
           "users",
           ["new_column"],
           postgresql_concurrently=True
       )
   ```

3. **Add columns as nullable first**, backfill, then add NOT NULL:
   ```python
   # Step 1: Add nullable
   op.add_column("users", sa.Column("new_col", sa.String(100), nullable=True))

   # Step 2: Backfill (in separate migration for large tables)
   op.execute("UPDATE users SET new_col = 'default' WHERE new_col IS NULL")

   # Step 3: Make NOT NULL
   op.alter_column("users", "new_col", nullable=False)
   ```

4. **Never change column types directly** on large tables. Use expand/contract:
   - Add new column
   - Migrate data
   - Update application to use new column
   - Drop old column

### For Development (SQLite)

SQLite has limited ALTER TABLE support. The `env.py` configuration enables batch mode for SQLite, which recreates tables for complex alterations.

## Directory Structure

```
alembic/
├── README.md           # This file
├── env.py              # Alembic environment configuration
├── script.py.mako      # Template for new migrations
└── versions/           # Migration scripts
    ├── .gitkeep
    └── 20250218_000000_initial_schema.py  # Initial baseline
```

## Environment Configuration

Migrations use the same database URL as the application, from:
- `DATABASE_URL` environment variable
- `.env` file
- Default: `sqlite:///./syfthub.db`

## Troubleshooting

### "Target database is not up to date"

Run pending migrations:
```bash
uv run alembic upgrade head
```

### "Can't locate revision identified by..."

The database references a migration that doesn't exist. This can happen if migrations were deleted. Options:
1. Re-add the missing migration
2. Manually update the `alembic_version` table
3. Reset with `alembic stamp head` (if you're sure the schema is correct)

### "Autogenerate detected no changes"

- Ensure all models are imported in `env.py`
- Check that model changes are saved
- Verify you're comparing against the correct database

### SQLite "batch mode" errors

SQLite doesn't support all ALTER TABLE operations. The migration system uses batch mode (recreate table) for SQLite. If you see errors:
1. Ensure `render_as_batch=True` is set for SQLite in `env.py`
2. For complex migrations, consider testing on PostgreSQL first

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Zero-Downtime Migrations](https://www.braintreepayments.com/blog/safe-operations-for-high-volume-postgresql/)
