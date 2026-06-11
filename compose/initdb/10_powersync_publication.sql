-- 10_powersync_publication.sql — the `powersync` PostgreSQL PUBLICATION.
--
-- THIS IS THE SYNC SECURITY BOUNDARY (ADR 0003). Only the tables added here are
-- ever exposed to the download flow. NEVER use `FOR ALL TABLES` — it would
-- replicate PII / server-only data (users, refresh_tokens, invitations,
-- admin_audit_logs, banking staging) through the sync channel.
--
-- PUBLISHED (S13.1 — client-sync tables WITHOUT any column to mask):
--   accounts, account_members, transactions, splits, categories,
--   budgets, budget_contributors
--   → all carried by an ADR 0003 bucket and free of sensitive columns. Enough
--     to prove connectivity + an initial published state. Final bucket
--     membership + column-level filters are S13.7.
--
-- DEFERRED to S13.7 (carry columns to mask / never-sync):
--   debts, share_requests, settlements, settlement_lines — carry account_id +
--   source_transaction_id (masked CONDITIONALLY per-recipient, ADR 0003 upd #145)
--   and materialization_trace (never synced). Column-level publication does not
--   fit: the OWNER must receive these, masking is per-recipient in the sync
--   rules (CASE WHEN ...), not global. Published in S13.7 excluding
--   materialization_trace at the column level.
--   budget_threshold_alerts, household — bucket membership decided in S13.7.
--
-- EXCLUDED permanently (server-only / PII, ADR 0003 + CONTEXT.md): users,
--   refresh_tokens, invitations, admin_audit_logs (physical name, not the
--   `audit_logs` alias), bank_account_external_refs, imported_transactions,
--   plus future sync_request_log / pending_actions / pat_tokens / device_tokens.
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
  allow text[] := ARRAY[
    'accounts', 'account_members',
    'transactions', 'splits',
    'categories',
    'budgets', 'budget_contributors'
  ];
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
END $$;
