-- Down migration: Revert token_prefix column length
-- WARNING: This will fail if any existing tokens have prefixes longer than 8 chars

ALTER TABLE api_tokens ALTER COLUMN token_prefix TYPE char(8);

COMMENT ON COLUMN api_tokens.token_prefix IS 'First 8 hex chars of token, stored for display identification';
