# Database Migrations

This directory contains SQL migration scripts for the SyftHub backend database.

## Migration Strategy

We use the **Expand-Contract** pattern for zero-downtime schema changes:

1. **EXPAND**: Add new columns/tables (backwards compatible)
2. **DEPLOY**: Roll out new application code
3. **CONTRACT**: Remove old columns/tables

## Running Migrations

### Development

```bash
# Connect to your database and run the migration
psql $DATABASE_URL -f backend/src/syfthub/database/migrations/001_unified_ledger_migration.sql
```

### Production

1. Review the migration script carefully
2. Run during low-traffic period if possible
3. Monitor for lock contention
4. Have rollback plan ready

```bash
# With lock timeout protection (already in scripts)
psql $DATABASE_URL -f 001_unified_ledger_migration.sql
```

## Migration Files

| File | Description | Status |
|------|-------------|--------|
| `001_unified_ledger_migration.sql` | Add accounting_api_token and accounting_account_id columns | **Run with PR #167** |
| `002_drop_accounting_password.sql` | Remove deprecated accounting_password column | **Run after full deployment** |

## Best Practices

1. **Always use transactions** - All migrations are wrapped in `BEGIN/COMMIT`
2. **Set lock_timeout** - Prevents indefinite waiting on locks
3. **Use IF NOT EXISTS / IF EXISTS** - Makes migrations idempotent
4. **Add column as nullable first** - Allows rolling deployments
5. **Use CONCURRENTLY for indexes** - When possible (outside transactions)
6. **Document prerequisites** - Especially for CONTRACT migrations

## Rollback

If migration fails:

```sql
-- For 001_unified_ledger_migration.sql
ALTER TABLE users DROP COLUMN IF EXISTS accounting_api_token;
ALTER TABLE users DROP COLUMN IF EXISTS accounting_account_id;
DROP INDEX IF EXISTS idx_users_accounting_account_id;
```
