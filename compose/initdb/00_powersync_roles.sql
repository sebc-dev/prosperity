-- 00_powersync_roles.sql — replication + storage roles. Idempotent (re-runnable).
--
-- Runs on a fresh volume via docker-entrypoint-initdb.d (dev), and is re-run by
-- the prod runbook (E16). Driver-safe: no psql meta-commands (\gexec etc.), so
-- the integration test can apply it through a plain connection too.

-- Least-privilege replication role for the PowerSync source connector.
-- LOGIN REPLICATION only — NOT superuser. SELECT grants are scoped to the
-- published tables in 10_powersync_publication.sql.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'powersync') THEN
    -- DEV password. Prod sets this via a secrets manager (runbook §Sécurité).
    CREATE ROLE powersync LOGIN REPLICATION PASSWORD 'powersync_dev';
  END IF;
END $$;

-- Owner of the dedicated bucket-storage database (created in
-- 05_powersync_storage_db.sql). PowerSync creates its own schema there, so the
-- owner's CREATE privilege is required.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ps_storage') THEN
    CREATE ROLE ps_storage LOGIN PASSWORD 'ps_storage_dev';
  END IF;
END $$;

-- Connect + schema usage on the source DB. `current_database()` keeps this
-- portable across dev (`prosperity`) and the integration testcontainer (whose
-- DB name differs).
DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO powersync', current_database());
END $$;
GRANT USAGE ON SCHEMA public TO powersync;
