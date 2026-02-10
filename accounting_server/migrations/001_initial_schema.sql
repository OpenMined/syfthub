-- Migration: 001_initial_schema
-- Description: Initial database schema for the Unified Global Ledger
-- Date: 2026-02-06

BEGIN;

-- ============================================
-- Extensions
-- ============================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- Accounts Table
-- ============================================
CREATE TABLE accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    type                VARCHAR(20) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
    balance             BIGINT NOT NULL DEFAULT 0,
    available_balance   BIGINT NOT NULL DEFAULT 0,
    currency            VARCHAR(10) NOT NULL DEFAULT 'CREDIT',
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version             INTEGER NOT NULL DEFAULT 1,

    -- Constraints
    CONSTRAINT chk_accounts_type CHECK (type IN ('user', 'system', 'escrow')),
    CONSTRAINT chk_accounts_status CHECK (status IN ('active', 'frozen', 'closed')),
    CONSTRAINT chk_accounts_positive_balance CHECK (balance >= 0),
    CONSTRAINT chk_accounts_positive_available CHECK (available_balance >= 0),
    CONSTRAINT chk_accounts_available_lte_balance CHECK (available_balance <= balance)
);

-- Indexes for accounts
CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_status ON accounts(status) WHERE status = 'active';
CREATE INDEX idx_accounts_type ON accounts(type);

COMMENT ON TABLE accounts IS 'User accounts holding internal credits';
COMMENT ON COLUMN accounts.balance IS 'Total balance in smallest currency unit';
COMMENT ON COLUMN accounts.available_balance IS 'Balance available for withdrawal (excluding holds)';
COMMENT ON COLUMN accounts.version IS 'Optimistic locking version number';

-- ============================================
-- Transactions Table
-- ============================================
CREATE TABLE transactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key         VARCHAR(255) NOT NULL,
    type                    VARCHAR(20) NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'pending',

    source_account_id       UUID REFERENCES accounts(id),
    destination_account_id  UUID REFERENCES accounts(id),

    amount                  BIGINT NOT NULL,
    fee                     BIGINT NOT NULL DEFAULT 0,
    currency                VARCHAR(10) NOT NULL DEFAULT 'CREDIT',

    external_reference      VARCHAR(255),
    provider_code           VARCHAR(50),

    description             TEXT,
    metadata                JSONB DEFAULT '{}',
    error_details           JSONB,

    parent_transaction_id   UUID REFERENCES transactions(id),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,

    -- Constraints
    CONSTRAINT chk_transactions_type CHECK (type IN ('transfer', 'deposit', 'withdrawal', 'refund', 'fee')),
    CONSTRAINT chk_transactions_status CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'reversed')),
    CONSTRAINT chk_transactions_positive_amount CHECK (amount > 0),
    CONSTRAINT chk_transactions_non_negative_fee CHECK (fee >= 0),
    CONSTRAINT chk_transactions_valid_accounts CHECK (
        (type = 'transfer' AND source_account_id IS NOT NULL AND destination_account_id IS NOT NULL) OR
        (type = 'deposit' AND destination_account_id IS NOT NULL) OR
        (type = 'withdrawal' AND source_account_id IS NOT NULL) OR
        (type IN ('refund', 'fee'))
    )
);

-- Unique constraint for idempotency
CREATE UNIQUE INDEX idx_transactions_idempotency ON transactions(idempotency_key);

-- Indexes for transactions
CREATE INDEX idx_transactions_source ON transactions(source_account_id, created_at DESC) WHERE source_account_id IS NOT NULL;
CREATE INDEX idx_transactions_destination ON transactions(destination_account_id, created_at DESC) WHERE destination_account_id IS NOT NULL;
CREATE INDEX idx_transactions_status_pending ON transactions(status, created_at) WHERE status IN ('pending', 'processing');
CREATE INDEX idx_transactions_type ON transactions(type);
CREATE INDEX idx_transactions_created_at ON transactions(created_at DESC);
CREATE INDEX idx_transactions_external_ref ON transactions(external_reference) WHERE external_reference IS NOT NULL;
CREATE INDEX idx_transactions_parent ON transactions(parent_transaction_id) WHERE parent_transaction_id IS NOT NULL;

COMMENT ON TABLE transactions IS 'All financial transactions (transfers, deposits, withdrawals, refunds)';
COMMENT ON COLUMN transactions.idempotency_key IS 'Client-provided key for deduplication';
COMMENT ON COLUMN transactions.external_reference IS 'Reference ID from external payment provider';

-- ============================================
-- Ledger Entries Table (Double-Entry Bookkeeping)
-- ============================================
CREATE TABLE ledger_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id  UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    account_id      UUID NOT NULL REFERENCES accounts(id),
    entry_type      VARCHAR(10) NOT NULL,
    amount          BIGINT NOT NULL,
    balance_after   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_ledger_entry_type CHECK (entry_type IN ('debit', 'credit')),
    CONSTRAINT chk_ledger_positive_amount CHECK (amount > 0)
);

-- Indexes for ledger entries
CREATE INDEX idx_ledger_entries_transaction ON ledger_entries(transaction_id);
CREATE INDEX idx_ledger_entries_account ON ledger_entries(account_id, created_at DESC);

COMMENT ON TABLE ledger_entries IS 'Double-entry ledger for audit trail';
COMMENT ON COLUMN ledger_entries.balance_after IS 'Running balance after this entry for audit';

-- ============================================
-- Payment Methods Table
-- ============================================
CREATE TABLE payment_methods (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    provider_code   VARCHAR(50) NOT NULL,
    type            VARCHAR(30) NOT NULL,
    status          VARCHAR(30) NOT NULL DEFAULT 'pending_verification',

    external_id     VARCHAR(255) NOT NULL,
    display_name    VARCHAR(100) NOT NULL,

    is_default      BOOLEAN NOT NULL DEFAULT false,
    is_withdrawable BOOLEAN NOT NULL DEFAULT false,

    metadata        JSONB DEFAULT '{}',
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_payment_method_type CHECK (type IN ('card', 'bank_account', 'wallet', 'crypto')),
    CONSTRAINT chk_payment_method_status CHECK (status IN ('pending_verification', 'verified', 'disabled')),
    CONSTRAINT uq_payment_method_provider_external UNIQUE (provider_code, external_id)
);

-- Indexes for payment methods
CREATE INDEX idx_payment_methods_account ON payment_methods(account_id);
CREATE INDEX idx_payment_methods_provider ON payment_methods(provider_code);

COMMENT ON TABLE payment_methods IS 'Linked external payment sources and destinations';
COMMENT ON COLUMN payment_methods.external_id IS 'Tokenized ID from the payment provider';
COMMENT ON COLUMN payment_methods.display_name IS 'User-friendly display (e.g., Visa •••• 4242)';

-- ============================================
-- Idempotency Keys Table
-- ============================================
CREATE TABLE idempotency_keys (
    key             VARCHAR(255) NOT NULL,
    user_id         UUID NOT NULL,
    endpoint        VARCHAR(100) NOT NULL,
    request_hash    VARCHAR(64) NOT NULL,
    response_code   INTEGER NOT NULL,
    response_body   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (key, user_id, endpoint)
);

-- Index for cleanup
CREATE INDEX idx_idempotency_keys_expires ON idempotency_keys(expires_at);

COMMENT ON TABLE idempotency_keys IS 'Cache for idempotent request handling';

-- ============================================
-- Webhooks Table
-- ============================================
CREATE TABLE webhooks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    url             VARCHAR(2048) NOT NULL,
    secret          VARCHAR(255) NOT NULL,
    events          TEXT[] NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_webhooks_status CHECK (status IN ('active', 'disabled'))
);

-- Indexes for webhooks
CREATE INDEX idx_webhooks_user ON webhooks(user_id);
CREATE INDEX idx_webhooks_status ON webhooks(status) WHERE status = 'active';
CREATE INDEX idx_webhooks_events ON webhooks USING GIN(events);

COMMENT ON TABLE webhooks IS 'User webhook subscriptions';

-- ============================================
-- Webhook Deliveries Table
-- ============================================
CREATE TABLE webhook_deliveries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id      UUID NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type      VARCHAR(100) NOT NULL,
    payload         JSONB NOT NULL,

    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    next_retry_at   TIMESTAMPTZ,

    response_code   INTEGER,
    response_body   TEXT,
    error_message   TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_delivery_status CHECK (status IN ('pending', 'delivered', 'failed'))
);

-- Indexes for webhook deliveries
CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);
CREATE INDEX idx_webhook_deliveries_pending ON webhook_deliveries(next_retry_at)
    WHERE status = 'pending';
CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries(status, created_at);

COMMENT ON TABLE webhook_deliveries IS 'Log of webhook delivery attempts';

-- ============================================
-- Functions and Triggers
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_payment_methods_updated_at
    BEFORE UPDATE ON payment_methods
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_webhooks_updated_at
    BEFORE UPDATE ON webhooks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- System Accounts (Fee Collection, etc.)
-- ============================================
-- These will be created by the application on first run,
-- but we can seed some here if needed

-- INSERT INTO accounts (id, user_id, type, status, currency)
-- VALUES (
--     '00000000-0000-0000-0000-000000000001',
--     '00000000-0000-0000-0000-000000000000',
--     'system',
--     'active',
--     'CREDIT'
-- );

COMMIT;
