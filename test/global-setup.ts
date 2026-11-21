import { resolve } from 'node:path';
import { PostgreSqlContainer } from '@testcontainers/postgresql';
import { sql } from 'kysely';
import type { TestProject } from 'vitest/node';
import { migrateToLatest } from '../src/db/migrate.ts';
import { MIGRATOR_ROLE, provisionMigrator } from '../src/db/provision.ts';
import { TEMPLATE_DATABASE, databaseUri, openDatabase } from './db.ts';

declare module 'vitest' {
  export interface ProvidedContext {
    pgAdminUri: string;
  }
}

// Image épinglée par digest (T-01-19) : mise à jour par PR dédiée uniquement.
const POSTGRES_IMAGE =
  'postgres:18.7-trixie@sha256:eb63372c1e05c755f55fa30cbd07aecc443676fc6c0fa90b9002d01537841e1a';

const MIGRATIONS_DIR = resolve(import.meta.dirname, '..', 'db', 'migrations');

/**
 * Un conteneur PostgreSQL 18.7 par run : rôle de migration provisionné par l'administrateur du
 * conteneur, base template possédée par ce rôle, migrations jouées sous ce rôle (jamais en
 * superutilisateur, D-10). Chaque fichier de test copie ensuite le template.
 */
export default async function setup(project: TestProject): Promise<() => Promise<void>> {
  const container = await new PostgreSqlContainer(POSTGRES_IMAGE).start();
  const adminUri = container.getConnectionUri();
  const admin = openDatabase(adminUri);
  try {
    await provisionMigrator(admin);
    await sql`CREATE DATABASE ${sql.id(TEMPLATE_DATABASE)} OWNER ${sql.id(MIGRATOR_ROLE)}`.execute(
      admin,
    );
  } finally {
    await admin.destroy();
  }
  const migrator = openDatabase(databaseUri(adminUri, TEMPLATE_DATABASE), MIGRATOR_ROLE);
  try {
    const identity = await sql<{ current_user: string }>`SELECT current_user`.execute(migrator);
    if (identity.rows[0]?.current_user !== MIGRATOR_ROLE) {
      throw new Error(`les migrations doivent tourner sous ${MIGRATOR_ROLE}`);
    }
    await migrateToLatest(migrator, MIGRATIONS_DIR);
  } finally {
    // Un template ne doit avoir aucune connexion ouverte au moment de la copie.
    await migrator.destroy();
  }
  project.provide('pgAdminUri', adminUri);
  return async () => {
    await container.stop();
  };
}
