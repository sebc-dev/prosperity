ALTER TABLE envelopes
    ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_envelopes_account_archived ON envelopes(bank_account_id, archived);
