import { sql } from 'kysely';
import type { Kysely } from 'kysely';

export const MIGRATOR_ROLE = 'prosperity_migrator';

/**
 * Crée, s'il n'existe pas, le rôle qui exécute les migrations. Il ne peut pas être créé par
 * elles : cette fonction est jouée par un administrateur du cluster (le superutilisateur du
 * conteneur en test, l'opérateur au déploiement), hors migration.
 *
 * Le rôle possède la base et le schéma applicatifs ; `CREATEROLE` ne lui sert qu'à créer le rôle
 * applicatif dans la migration 0001 (PostgreSQL 18 lui interdit d'accorder SUPERUSER, BYPASSRLS
 * ou REPLICATION). `LOGIN` et mot de passe sont posés hors git au provisioning.
 */
export async function provisionMigrator(admin: Kysely<unknown>): Promise<void> {
  await sql`DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prosperity_migrator') THEN
      CREATE ROLE prosperity_migrator NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB CREATEROLE NOBYPASSRLS NOREPLICATION;
    END IF;
  END $$`.execute(admin);
}
