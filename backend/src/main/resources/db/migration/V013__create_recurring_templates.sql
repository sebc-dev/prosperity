CREATE TABLE recurring_templates (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES bank_accounts(id),
    amount NUMERIC(19,4) NOT NULL,
    description VARCHAR(500),
    category_id UUID REFERENCES categories(id),
    frequency VARCHAR(20) NOT NULL,
    day_of_month INT,
    next_due_date DATE NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_recurring_templates_account_id ON recurring_templates(account_id);
CREATE INDEX idx_recurring_templates_next_due_date ON recurring_templates(next_due_date);
