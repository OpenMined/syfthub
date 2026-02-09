-- Migration: 002_drop_accounting_password
-- Description: Remove deprecated accounting_password column (CONTRACT phase)
-- Date: 2026-02-09
-- Author: Unified Ledger Migration PR #167
--
-- IMPORTANT: Only run this migration AFTER all application instances
-- have been deployed with the new Unified Ledger code.
--
-- Prerequisites:
-- 1. All instances running new code (using accounting_api_token)
-- 2. No rollback to old code expected
-- 3. Verify no queries reference accounting_password column
--
-- Verification query before running:
-- SELECT COUNT(*) FROM users WHERE accounting_password IS NOT NULL;

BEGIN;

SET LOCAL lock_timeout = '5s';

-- ============================================
-- Drop deprecated column
-- ============================================

-- Remove the old accounting_password column
-- This is safe after all code uses accounting_api_token
ALTER TABLE users
    DROP COLUMN IF EXISTS accounting_password;

COMMIT;
