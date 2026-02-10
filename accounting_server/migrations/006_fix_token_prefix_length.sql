-- Migration: Fix token_prefix column length
-- Purpose: Align database column with code that generates 16-char hex prefixes
--
-- The ApiToken.create() method generates an 8-byte random prefix and converts
-- it to hex, producing 16 characters. However, the original migration created
-- the column as char(8), causing inserts to fail.
--
-- This migration expands the column to char(16) to match the code.

-- Alter the token_prefix column from char(8) to char(16)
ALTER TABLE api_tokens ALTER COLUMN token_prefix TYPE char(16);

-- Update the comment to reflect the correct length
COMMENT ON COLUMN api_tokens.token_prefix IS 'First 16 hex chars of token (8 bytes), stored for display identification and efficient lookups';
