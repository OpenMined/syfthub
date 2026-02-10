-- Migration Rollback: 005_add_dead_letter_webhooks
-- Description: Reverts the dead letter webhooks table
-- Date: 2026-02-09
--
-- WARNING: Rolling back will drop the dead_letter_webhooks table
-- and all investigation data stored in it. Back up the table if needed.

BEGIN;

-- Drop the dead letter webhooks table and all its indexes
DROP TABLE IF EXISTS dead_letter_webhooks CASCADE;

COMMIT;
