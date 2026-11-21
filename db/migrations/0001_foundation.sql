-- 0001_foundation : socle base de données (D-10). Migration forward-only, sans `down`.
-- À exécuter sous le rôle `prosperity_migrator` (jamais en superutilisateur), provisionné hors
-- migration par `src/db/provision.ts`. `LOGIN` et mots de passe des rôles `prosperity_migrator`
-- et `prosperity_app` sont posés hors git au provisioning. Aucune table métier ici.
-- `uuidv7()` est natif dans PostgreSQL 18 : aucune extension à créer.

-- Rôle applicatif : aucun droit DDL, aucune propriété d'objet, jamais de contournement de RLS.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prosperity_app') THEN
    CREATE ROLE prosperity_app NOLOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;

-- Personne ne crée d'objet dans `public` hors du propriétaire de la base (pg_database_owner).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Schéma applicatif : possédé par le rôle de migration qui exécute ce fichier.
CREATE SCHEMA IF NOT EXISTS prosperity;
GRANT USAGE ON SCHEMA prosperity TO prosperity_app;

-- Droits de lecture/écriture du rôle app sur les tables que le rôle de migration créera.
ALTER DEFAULT PRIVILEGES IN SCHEMA prosperity
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO prosperity_app;
