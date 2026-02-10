-- Migration: 002_add_transfer_confirmation (DOWN)
-- Description: Remove confirmation flow fields for P2P transfers
-- Date: 2026-02-07

BEGIN;

-- ============================================
-- Remove confirmation fields
-- ============================================
DROP INDEX IF EXISTS idx_transactions_confirmation_expires;
ALTER TABLE transactions DROP COLUMN IF EXISTS confirmation_token;
ALTER TABLE transactions DROP COLUMN IF EXISTS confirmation_expires_at;

-- ============================================
-- Restore original transaction status constraint
-- ============================================
-- First, update any rows with new statuses to a valid old status
UPDATE transactions SET status = 'pending' WHERE status = 'awaiting_confirmation';
UPDATE transactions SET status = 'failed' WHERE status = 'cancelled';

ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transactions_status;
ALTER TABLE transactions ADD CONSTRAINT chk_transactions_status CHECK (
    status IN ('pending', 'processing', 'completed', 'failed', 'reversed')
);

-- Restore original index
DROP INDEX IF EXISTS idx_transactions_status_pending;
CREATE INDEX idx_transactions_status_pending
    ON transactions(status, created_at)
    WHERE status IN ('pending', 'processing');

COMMIT;
