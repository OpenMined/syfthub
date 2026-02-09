-- Migration: 005_add_dead_letter_webhooks
-- Description: Adds webhook dead letter table for production failure tracking
-- Date: 2026-02-09
--
-- This migration adds a dead_letter_webhooks table for storing failed webhook
-- events that require investigation or retry. This is critical for production
-- reliability to ensure no financial events are lost.
--
-- Note: Confirmation flow support was already added in migration 002.

BEGIN;

-- ============================================
-- Create dead letter webhooks table
-- ============================================

-- Stores failed webhook events for investigation and retry
-- This is critical for production reliability - ensures no financial events are lost
CREATE TABLE IF NOT EXISTS dead_letter_webhooks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Webhook identification
    provider            VARCHAR(50) NOT NULL,
    event_type          VARCHAR(100),
    delivery_id         VARCHAR(255),

    -- Payload (truncated/hashed for security - no raw sensitive data)
    -- Store hash for deduplication, truncated preview for debugging
    payload_hash        VARCHAR(64) NOT NULL,
    payload_preview     TEXT,
    payload_size_bytes  INTEGER NOT NULL,

    -- Error information
    error_message       TEXT NOT NULL,
    error_code          VARCHAR(100),
    retryable           BOOLEAN NOT NULL DEFAULT false,

    -- Tracking
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempt_count       INTEGER NOT NULL DEFAULT 1,

    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_attempt_at     TIMESTAMPTZ,
    investigated_at     TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,

    -- Investigation notes
    resolution_notes    TEXT,
    resolved_by         VARCHAR(255),

    -- Constraints
    CONSTRAINT chk_dead_letter_status CHECK (
        status IN ('pending', 'retrying', 'investigating', 'resolved', 'ignored')
    )
);

-- Indexes for dead letter webhooks
-- Index for finding pending items that need attention
CREATE INDEX IF NOT EXISTS idx_dead_letter_webhooks_status
ON dead_letter_webhooks(status, created_at DESC)
WHERE status IN ('pending', 'retrying');

-- Index for filtering by provider
CREATE INDEX IF NOT EXISTS idx_dead_letter_webhooks_provider
ON dead_letter_webhooks(provider, created_at DESC);

-- Index for finding retryable failures
CREATE INDEX IF NOT EXISTS idx_dead_letter_webhooks_retryable
ON dead_letter_webhooks(retryable, created_at)
WHERE status = 'pending' AND retryable = true;

-- Unique constraint to prevent duplicate entries for the same webhook delivery
CREATE UNIQUE INDEX IF NOT EXISTS idx_dead_letter_webhooks_delivery
ON dead_letter_webhooks(provider, delivery_id)
WHERE delivery_id IS NOT NULL;

COMMENT ON TABLE dead_letter_webhooks IS 'Failed webhook events requiring investigation or retry';
COMMENT ON COLUMN dead_letter_webhooks.payload_hash IS 'SHA-256 hash of original payload for deduplication';
COMMENT ON COLUMN dead_letter_webhooks.payload_preview IS 'First 1000 chars with sensitive fields redacted';
COMMENT ON COLUMN dead_letter_webhooks.retryable IS 'Whether this failure is transient and can be retried';

COMMIT;
