-- Migration: Create API tokens table
-- Purpose: Enable programmatic access to user accounts with scoped permissions

CREATE TABLE api_tokens (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         text NOT NULL,
    token_prefix    char(16) NOT NULL,
    token_hash      bytea NOT NULL,
    name            text NOT NULL,
    scopes          text[] NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz,
    last_used_at    timestamptz,
    last_used_ip    inet,
    revoked_at      timestamptz,
    revoked_reason  text,
    version         integer NOT NULL DEFAULT 1,

    CONSTRAINT chk_name_length CHECK (char_length(name) BETWEEN 1 AND 100)
);

-- Unique index on token hash for efficient authentication lookups
-- Only index non-revoked tokens since revoked tokens cannot be used
CREATE UNIQUE INDEX idx_api_tokens_hash ON api_tokens (token_hash) WHERE revoked_at IS NULL;

-- Index for listing user's tokens, ordered by creation date
-- Only index non-revoked tokens since those are the ones we display
CREATE INDEX idx_api_tokens_user_id ON api_tokens (user_id, created_at DESC) WHERE revoked_at IS NULL;

-- Add comments for documentation
COMMENT ON TABLE api_tokens IS 'API tokens for programmatic access to user accounts';
COMMENT ON COLUMN api_tokens.token_prefix IS 'First 16 hex chars of token (8 bytes), stored for display identification and efficient lookups';
COMMENT ON COLUMN api_tokens.token_hash IS 'SHA-256 hash of the full token';
COMMENT ON COLUMN api_tokens.scopes IS 'Array of permission scopes: accounts:read, accounts:write, transactions:read, deposits:write, withdrawals:write, transfers:write, payment-methods:read, payment-methods:write';
COMMENT ON COLUMN api_tokens.last_used_ip IS 'IP address of last token usage';
