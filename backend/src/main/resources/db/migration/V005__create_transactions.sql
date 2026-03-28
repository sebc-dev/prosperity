CREATE TABLE transactions (
    id UUID PRIMARY KEY,
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id),
    amount_cents BIGINT NOT NULL,
    description VARCHAR(500),
    category VARCHAR(100),
    transaction_date DATE NOT NULL,
    source VARCHAR(20) NOT NULL,
    state VARCHAR(30) NOT NULL DEFAULT 'MANUAL_UNMATCHED',
    plaid_transaction_id VARCHAR(255),
    pointed BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
