CREATE TABLE account_access (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(id),
    access_level VARCHAR(20) NOT NULL,
    UNIQUE(user_id, bank_account_id)
);
