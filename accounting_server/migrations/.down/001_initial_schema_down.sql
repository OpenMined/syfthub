-- Rollback Migration: 001_initial_schema
-- Description: Drop all tables created in initial schema
-- Date: 2026-02-06

BEGIN;

-- Drop triggers first
DROP TRIGGER IF EXISTS update_accounts_updated_at ON accounts;
DROP TRIGGER IF EXISTS update_payment_methods_updated_at ON payment_methods;
DROP TRIGGER IF EXISTS update_webhooks_updated_at ON webhooks;

-- Drop function
DROP FUNCTION IF EXISTS update_updated_at_column();

-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS webhook_deliveries;
DROP TABLE IF EXISTS webhooks;
DROP TABLE IF EXISTS idempotency_keys;
DROP TABLE IF EXISTS payment_methods;
DROP TABLE IF EXISTS ledger_entries;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS accounts;

-- Drop extensions (optional - may be used by other schemas)
-- DROP EXTENSION IF EXISTS "pgcrypto";
-- DROP EXTENSION IF EXISTS "uuid-ossp";

COMMIT;
