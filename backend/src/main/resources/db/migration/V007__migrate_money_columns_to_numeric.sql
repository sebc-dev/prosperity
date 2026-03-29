-- ADR-0003: Migrate monetary columns from BIGINT cents to NUMERIC(19,4)
-- Converts stored cent values to decimal (divide by 100) and renames columns.

-- bank_accounts: balance_cents → balance
ALTER TABLE bank_accounts
    ALTER COLUMN balance_cents TYPE NUMERIC(19,4) USING balance_cents / 100.0;
ALTER TABLE bank_accounts
    RENAME COLUMN balance_cents TO balance;
ALTER TABLE bank_accounts
    ALTER COLUMN balance SET DEFAULT 0;

-- transactions: amount_cents → amount
ALTER TABLE transactions
    ALTER COLUMN amount_cents TYPE NUMERIC(19,4) USING amount_cents / 100.0;
ALTER TABLE transactions
    RENAME COLUMN amount_cents TO amount;

-- envelopes: budget_cents → budget
ALTER TABLE envelopes
    ALTER COLUMN budget_cents TYPE NUMERIC(19,4) USING budget_cents / 100.0;
ALTER TABLE envelopes
    RENAME COLUMN budget_cents TO budget;
ALTER TABLE envelopes
    ALTER COLUMN budget SET DEFAULT 0;

-- envelope_allocations: allocated_amount_cents → allocated_amount
ALTER TABLE envelope_allocations
    ALTER COLUMN allocated_amount_cents TYPE NUMERIC(19,4) USING allocated_amount_cents / 100.0;
ALTER TABLE envelope_allocations
    RENAME COLUMN allocated_amount_cents TO allocated_amount;
