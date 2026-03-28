CREATE TABLE envelopes (
    id UUID PRIMARY KEY,
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id),
    name VARCHAR(100) NOT NULL,
    scope VARCHAR(20) NOT NULL,
    owner_id UUID REFERENCES users(id),
    budget_cents BIGINT NOT NULL DEFAULT 0,
    rollover_policy VARCHAR(20) NOT NULL DEFAULT 'RESET',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE envelope_allocations (
    id UUID PRIMARY KEY,
    envelope_id UUID NOT NULL REFERENCES envelopes(id),
    month VARCHAR(7) NOT NULL,
    allocated_amount_cents BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
