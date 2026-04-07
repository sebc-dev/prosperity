CREATE TABLE transaction_splits (
    id UUID PRIMARY KEY,
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id),
    amount NUMERIC(19,4) NOT NULL,
    description VARCHAR(500)
);
CREATE INDEX idx_transaction_splits_transaction_id ON transaction_splits(transaction_id);
