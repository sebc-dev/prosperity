-- Curated French household categories mapped to Plaid PFCv2 taxonomy
-- Using deterministic UUIDs (pattern: a0000000-0000-0000-0000-00000000XXYY)
-- XX = root index (01-14), YY = child index (01-99), 00 = root itself

-- ROOT 01: Alimentation & Restauration (FOOD_AND_DRINK)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000100', 'Alimentation & Restauration', NULL, 'FOOD_AND_DRINK', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000101', 'Courses', 'a0000000-0000-0000-0000-000000000100', 'FOOD_AND_DRINK_GROCERIES', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000102', 'Restaurant', 'a0000000-0000-0000-0000-000000000100', 'FOOD_AND_DRINK_RESTAURANT', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000103', 'Cafe', 'a0000000-0000-0000-0000-000000000100', 'FOOD_AND_DRINK_COFFEE', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 02: Transport (TRANSPORTATION)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000200', 'Transport', NULL, 'TRANSPORTATION', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000201', 'Carburant', 'a0000000-0000-0000-0000-000000000200', 'TRANSPORTATION_GAS', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000202', 'Transports en commun', 'a0000000-0000-0000-0000-000000000200', 'TRANSPORTATION_PUBLIC_TRANSIT', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000203', 'Parking', 'a0000000-0000-0000-0000-000000000200', 'TRANSPORTATION_PARKING', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 03: Logement & Charges (RENT_AND_UTILITIES)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000300', 'Logement & Charges', NULL, 'RENT_AND_UTILITIES', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000301', 'Loyer', 'a0000000-0000-0000-0000-000000000300', 'RENT_AND_UTILITIES_RENT', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000302', 'Electricite & Gaz', 'a0000000-0000-0000-0000-000000000300', 'RENT_AND_UTILITIES_GAS_AND_ELECTRIC', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000303', 'Internet & Telephone', 'a0000000-0000-0000-0000-000000000300', 'RENT_AND_UTILITIES_INTERNET_AND_TELECOM', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000304', 'Eau', 'a0000000-0000-0000-0000-000000000300', 'RENT_AND_UTILITIES_WATER', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 04: Sante (MEDICAL)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000400', 'Sante', NULL, 'MEDICAL', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000401', 'Pharmacie', 'a0000000-0000-0000-0000-000000000400', 'MEDICAL_PHARMACIES', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000402', 'Medecin', 'a0000000-0000-0000-0000-000000000400', 'MEDICAL_PRIMARY_CARE', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000403', 'Dentiste', 'a0000000-0000-0000-0000-000000000400', 'MEDICAL_DENTAL', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 05: Loisirs & Culture (ENTERTAINMENT)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000500', 'Loisirs & Culture', NULL, 'ENTERTAINMENT', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000501', 'Sorties', 'a0000000-0000-0000-0000-000000000500', 'ENTERTAINMENT_OTHER_ENTERTAINMENT', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000502', 'Streaming', 'a0000000-0000-0000-0000-000000000500', 'ENTERTAINMENT_TV_AND_MOVIES', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000503', 'Sports & Activites', 'a0000000-0000-0000-0000-000000000500', 'ENTERTAINMENT_GYMS_AND_FITNESS', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 06: Achats & Shopping (GENERAL_MERCHANDISE)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000600', 'Achats & Shopping', NULL, 'GENERAL_MERCHANDISE', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000601', 'Vetements', 'a0000000-0000-0000-0000-000000000600', 'GENERAL_MERCHANDISE_CLOTHING', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000602', 'Electronique', 'a0000000-0000-0000-0000-000000000600', 'GENERAL_MERCHANDISE_ELECTRONICS', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000603', 'Divers', 'a0000000-0000-0000-0000-000000000600', 'GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 07: Services (GENERAL_SERVICES)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000700', 'Services', NULL, 'GENERAL_SERVICES', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000701', 'Assurance', 'a0000000-0000-0000-0000-000000000700', 'GENERAL_SERVICES_INSURANCE', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000702', 'Education', 'a0000000-0000-0000-0000-000000000700', 'GENERAL_SERVICES_EDUCATION', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 08: Remboursements (LOAN_PAYMENTS)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000800', 'Remboursements', NULL, 'LOAN_PAYMENTS', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000801', 'Credit immobilier', 'a0000000-0000-0000-0000-000000000800', 'LOAN_PAYMENTS_MORTGAGE', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000802', 'Credit conso', 'a0000000-0000-0000-0000-000000000800', 'LOAN_PAYMENTS_PERSONAL_LOANS', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 09: Revenus (INCOME)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000900', 'Revenus', NULL, 'INCOME', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000901', 'Salaire', 'a0000000-0000-0000-0000-000000000900', 'INCOME_WAGES', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000902', 'Interets', 'a0000000-0000-0000-0000-000000000900', 'INCOME_INTEREST_EARNED', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000000903', 'Remboursement impots', 'a0000000-0000-0000-0000-000000000900', 'INCOME_TAX_REFUND', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 10: Virements (TRANSFER_IN)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001000', 'Virements', NULL, 'TRANSFER_IN', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001001', 'Epargne', 'a0000000-0000-0000-0000-000000001000', 'TRANSFER_IN_SAVINGS', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001002', 'Virement compte', 'a0000000-0000-0000-0000-000000001000', 'TRANSFER_IN_ACCOUNT_TRANSFER', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 11: Frais bancaires (BANK_FEES) -- no children
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001100', 'Frais bancaires', NULL, 'BANK_FEES', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 12: Impots & Dons (GOVERNMENT_AND_NON_PROFIT)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001200', 'Impots & Dons', NULL, 'GOVERNMENT_AND_NON_PROFIT', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001201', 'Impots', 'a0000000-0000-0000-0000-000000001200', 'GOVERNMENT_AND_NON_PROFIT_TAX', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001202', 'Dons', 'a0000000-0000-0000-0000-000000001200', 'GOVERNMENT_AND_NON_PROFIT_DONATIONS', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 13: Soins personnels (PERSONAL_CARE)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001300', 'Soins personnels', NULL, 'PERSONAL_CARE', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001301', 'Coiffeur & Beaute', 'a0000000-0000-0000-0000-000000001300', 'PERSONAL_CARE_HAIR_AND_BEAUTY', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001302', 'Salle de sport', 'a0000000-0000-0000-0000-000000001300', 'PERSONAL_CARE_GYMS_AND_FITNESS', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 14: Voyages (TRAVEL)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001400', 'Voyages', NULL, 'TRAVEL', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001401', 'Hebergement', 'a0000000-0000-0000-0000-000000001400', 'TRAVEL_LODGING', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001402', 'Vols', 'a0000000-0000-0000-0000-000000001400', 'TRAVEL_FLIGHTS', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001403', 'Location voiture', 'a0000000-0000-0000-0000-000000001400', 'TRAVEL_CAR_RENTAL', TRUE, '2026-01-01T00:00:00Z');

-- ROOT 15: Virements sortants (TRANSFER_OUT)
INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001500', 'Virements sortants', NULL, 'TRANSFER_OUT', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001501', 'Epargne sortante', 'a0000000-0000-0000-0000-000000001500', 'TRANSFER_OUT_SAVINGS', TRUE, '2026-01-01T00:00:00Z');

INSERT INTO categories (id, name, parent_id, plaid_category_id, is_system, created_at)
VALUES ('a0000000-0000-0000-0000-000000001502', 'Virement sortant compte', 'a0000000-0000-0000-0000-000000001500', 'TRANSFER_OUT_ACCOUNT_TRANSFER', TRUE, '2026-01-01T00:00:00Z');
