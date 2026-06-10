-- 05_powersync_storage_db.sql — dedicated bucket-storage database.
--
-- PowerSync requires its bucket storage to be SEPARATE from the source. In dev
-- this is a second database on the same Postgres instance (PG17 ≥ 14 allows
-- source + storage on one server). Prod (E16) may split the instances.
--
-- psql-only: `CREATE DATABASE` cannot run inside a transaction/DO block, so this
-- uses the `\gexec` idempotent pattern. It runs via psql in dev initdb and in
-- the prod runbook. The integration test does NOT apply this file (it needs a
-- driver connection and the storage DB is irrelevant to publication assertions).
SELECT 'CREATE DATABASE powersync_storage OWNER ps_storage'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'powersync_storage')
\gexec
