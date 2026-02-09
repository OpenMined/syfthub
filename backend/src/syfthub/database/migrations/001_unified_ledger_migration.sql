-- Migration: 001_unified_ledger_migration
-- Description: Migrate accounting fields for Unified Global Ledger integration
-- Date: 2026-02-09
-- Author: Unified Ledger Migration PR #167
--
-- This migration adds new columns for the Unified Global Ledger while
-- maintaining backwards compatibility during the deployment window.
--
-- Strategy: Expand-Contract Migration
-- 1. EXPAND: Add new columns (this migration)
-- 2. DEPLOY: Deploy new code that uses new columns
-- 3. CONTRACT: Remove old column (separate migration after full deployment)

BEGIN;

-- Set a lock timeout to prevent long waits during migration
SET LOCAL lock_timeout = '5s';

-- ============================================
-- Add new accounting columns
-- ============================================

-- Add accounting_api_token column (nullable for backwards compatibility)
-- Stores the API token for Unified Global Ledger (at_* format)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS accounting_api_token VARCHAR(500) DEFAULT NULL;

COMMENT ON COLUMN users.accounting_api_token IS
    'API token for Unified Global Ledger authentication (at_* format). Replaces accounting_password.';

-- Add accounting_account_id column (nullable for backwards compatibility)
-- Stores the UUID of the user''s account in the ledger
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS accounting_account_id VARCHAR(36) DEFAULT NULL;

COMMENT ON COLUMN users.accounting_account_id IS
    'UUID of the user account in Unified Global Ledger';

-- ============================================
-- Create index for account_id lookups
-- ============================================

-- Index for looking up users by their ledger account
-- Using CONCURRENTLY to avoid blocking reads/writes
-- Note: Run this command separately if needed, as CONCURRENTLY
-- cannot be used inside a transaction block
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_accounting_account_id
--     ON users(accounting_account_id)
--     WHERE accounting_account_id IS NOT NULL;

-- Non-concurrent version for transaction safety
CREATE INDEX IF NOT EXISTS idx_users_accounting_account_id
    ON users(accounting_account_id)
    WHERE accounting_account_id IS NOT NULL;

-- ============================================
-- Backwards Compatibility Note
-- ============================================
--
-- The accounting_password column is NOT dropped in this migration.
-- This allows rolling deployments where old code can still read/write
-- the password field while new code uses the API token.
--
-- After all instances are deployed with the new code, run:
-- 002_drop_accounting_password.sql

COMMIT;
