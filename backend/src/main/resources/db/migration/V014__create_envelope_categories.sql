CREATE TABLE envelope_categories (
    envelope_id UUID NOT NULL REFERENCES envelopes(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    PRIMARY KEY (envelope_id, category_id)
);

CREATE INDEX idx_envelope_categories_category_id ON envelope_categories(category_id);
