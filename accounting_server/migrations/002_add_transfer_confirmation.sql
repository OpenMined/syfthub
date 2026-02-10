-- Migration: 002_add_transfer_confirmation
-- Description: Add confirmation flow fields for P2P transfers
-- Date: 2026-02-07

BEGIN;

-- ============================================
-- Add new transaction statuses
-- ============================================
-- Drop the old constraint
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transactions_status;

-- Increase status column size to accommodate 'awaiting_confirmation' (21 chars)
ALTER TABLE transactions ALTER COLUMN status TYPE VARCHAR(30);

-- Add the new constraint with additional statuses
ALTER TABLE transactions ADD CONSTRAINT chk_transactions_status CHECK (
    status IN ('pending', 'awaiting_confirmation', 'processing', 'completed', 'failed', 'cancelled', 'reversed')
);

-- ============================================
-- Add confirmation fields to transactions
-- ============================================
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS confirmation_token VARCHAR(255);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS confirmation_expires_at TIMESTAMPTZ;

-- Index for finding pending confirmations that need to be expired
CREATE INDEX IF NOT EXISTS idx_transactions_confirmation_expires
    ON transactions(confirmation_expires_at)
    WHERE status = 'awaiting_confirmation' AND confirmation_expires_at IS NOT NULL;

-- Update the pending status index to include awaiting_confirmation
DROP INDEX IF EXISTS idx_transactions_status_pending;
CREATE INDEX idx_transactions_status_pending
    ON transactions(status, created_at)
    WHERE status IN ('pending', 'awaiting_confirmation', 'processing');

COMMENT ON COLUMN transactions.confirmation_token IS 'HMAC token for P2P transfer recipient confirmation';
COMMENT ON COLUMN transactions.confirmation_expires_at IS 'Expiration time for the confirmation token';

COMMIT;
