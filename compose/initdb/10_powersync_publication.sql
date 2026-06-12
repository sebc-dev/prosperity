-- 10_powersync_publication.sql — the `powersync` PostgreSQL PUBLICATION.
--
-- THIS IS THE SYNC SECURITY BOUNDARY (ADR 0003). Only the tables added here are
-- ever exposed to the download flow. NEVER use `FOR ALL TABLES` — it would
-- replicate PII / server-only data (users, refresh_tokens, invitations,
-- admin_audit_logs, banking staging) through the sync channel.
--
-- PUBLISHED (full-column — no column hidden at the replication layer):
--   accounts, account_members, transactions, splits, categories,
--   budgets, budget_contributors            (S13.1 — ADR 0003 buckets)
--   share_requests, settlement_lines, users_public   (S13.7)
--   → all carried by an ADR 0003 bucket. `share_requests.source_transaction_id`
--     IS hidden from the debtor, but PER-RECIPIENT in the sync rules (the OWNER
--     must receive it), so the column stays published. `users_public` is the
--     trigger-built non-PII identity projection ({user_id, display_name, role}).
--
-- PUBLISHED with a COLUMN-LIST (S13.7, D-MAT):
--   debts — every column EXCEPT `materialization_trace`. That column is a
--     server-only forensic marker (ADR 0003 / CONTEXT.md) and must NEVER reach
--     a client, so it is cut at the replication layer (the lowest, safest
--     boundary) rather than masked per-query. `account_id` /
--     `source_transaction_id` ARE published (the creditor/owner must receive
--     them) — they are masked PER-RECIPIENT in the sync rules (NULL AS col),
--     not globally. PG15+ column-lists must include the replica-identity column
--     (PK `id`), which this list does.
--
-- NOT PUBLISHED — fail-closed (S13.7, D-SET):
--   settlements — per-participant routing is a multi-hop
--     (settlement→lines→debts→user) inexpressible mono-table, and
--     `settlements.note` is free-text PII. Settlement *lines* (no PII) ARE
--     published and route mono-hop by debt_id; `settlements` stays REST-only.
--   budget_threshold_alerts, household — server-only / singleton, no client need.
--
-- EXCLUDED permanently (server-only / PII, ADR 0003 + CONTEXT.md): users,
--   refresh_tokens, invitations, admin_audit_logs (physical name, not the
--   `audit_logs` alias), bank_account_external_refs, imported_transactions,
--   sync_request_log, settlements, debts.materialization_trace, plus future
--   pending_actions / pat_tokens / device_tokens.
--
-- Idempotent + NON-DESTRUCTIVE + table-existence-guarded. On a fresh volume the
-- app tables do not exist yet (compose/initdb runs BEFORE `alembic upgrade
-- head`), so this creates an EMPTY publication and adds nothing — the
-- replication slot can still attach. Re-run this AFTER migrations to add the
-- tables (the runbook documents the sequence). ADD-only means it never drops a
-- slot's publication out from under the running service; the integration test
-- enforces that the final set equals the allowlist exactly.
DO $$
DECLARE
  -- Full-column tables (every column safe to replicate). `debts` is handled
  -- separately below (column-list excluding materialization_trace, D-MAT).
  allow text[] := ARRAY[
    'accounts', 'account_members',
    'transactions', 'splits',
    'categories',
    'budgets', 'budget_contributors',
    'share_requests', 'settlement_lines', 'users_public'
  ];
  -- debts column-list — EXCLUDES materialization_trace (server-only) from the
  -- PUBLICATION, so the column is never carried by logical replication.
  debts_cols text := 'id, from_user_id, to_user_id, amount_cents, currency, '
                  || 'account_id, source_transaction_id, origin, share_ratio, created_at';
  t text;
BEGIN
  -- CREATE PUBLICATION has no IF NOT EXISTS; guard via the catalog.
  IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'powersync') THEN
    EXECUTE 'CREATE PUBLICATION powersync';
  END IF;

  FOREACH t IN ARRAY allow LOOP
    -- Add the table only if it already exists AND is not already published.
    IF EXISTS (
      SELECT 1 FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = t
    ) AND NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'powersync' AND schemaname = 'public' AND tablename = t
    ) THEN
      EXECUTE format('ALTER PUBLICATION powersync ADD TABLE %I', t);
      -- Least privilege: SELECT only on published tables.
      EXECUTE format('GRANT SELECT ON %I TO powersync', t);
    END IF;
  END LOOP;

  -- debts: published with a COLUMN-LIST (D-MAT — never materialization_trace).
  -- Same existence + presence guard as the loop, so re-running is idempotent and
  -- the script stays non-destructive. The integration test
  -- (test_materialization_trace_never_published) verifies the column-list
  -- against the live catalog, catching any drift loudly.
  IF EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = 'debts'
  ) AND NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'powersync' AND schemaname = 'public' AND tablename = 'debts'
  ) THEN
    EXECUTE format('ALTER PUBLICATION powersync ADD TABLE debts (%s)', debts_cols);
    -- TABLE-level SELECT (not column-level): PowerSync's initial snapshot runs
    -- `SELECT * FROM debts`, which needs SELECT on the whole table. A
    -- column-level grant would deny that and break replication. The column-list
    -- on the PUBLICATION above already keeps materialization_trace out of the
    -- replicated stream, and the sync rules project explicit columns (never
    -- materialization_trace) into buckets — so the server-only marker still
    -- never reaches a client, while the snapshot query can run.
    EXECUTE 'GRANT SELECT ON debts TO powersync';
  END IF;
END $$;
