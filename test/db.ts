import { randomUUID } from 'node:crypto';
import { Kysely, PostgresDialect, sql } from 'kysely';
import { Pool } from 'pg';
import { inject } from 'vitest';
import { MIGRATOR_ROLE } from '../src/db/provision.ts';

/** Base template migrée une fois par `test/global-setup.ts`, copiée pour chaque fichier de test. */
export const TEMPLATE_DATABASE = 'prosperity_tpl';

/** Même serveur et mêmes identifiants que `adminUri`, base `name`. */
export function databaseUri(adminUri: string, name: string): string {
  const url = new URL(adminUri);
  url.pathname = `/${name}`;
  return url.toString();
}

/**
 * Kysely sur `uri`. Avec `role`, chaque session démarre sous ce rôle (option de connexion
 * `-c role=`) : le rôle de migration n'a pas de `LOGIN` en test, l'administrateur prend son
 * identité dès l'ouverture de la session et perd ses propres privilèges.
 */
export function openDatabase(uri: string, role?: string): Kysely<unknown> {
  const pool = new Pool({
    connectionString: uri,
    max: 4,
    ...(role === undefined ? {} : { options: `-c role=${role}` }),
  });
  return new Kysely<unknown>({ dialect: new PostgresDialect({ pool }) });
}

function uniqueName(): string {
  const worker = process.env['VITEST_POOL_ID'] ?? '0';
  return `t_${worker}_${randomUUID().replaceAll('-', '').slice(0, 16)}`;
}

/** Exécute `work` sur une connexion d'administration éphémère (base de maintenance). */
async function withMaintenance(
  adminUri: string,
  work: (admin: Kysely<unknown>) => Promise<unknown>,
): Promise<void> {
  const admin = openDatabase(adminUri);
  try {
    await work(admin);
  } finally {
    await admin.destroy();
  }
}

async function dropDatabase(adminUri: string, name: string): Promise<void> {
  await withMaintenance(adminUri, (admin) =>
    sql`DROP DATABASE IF EXISTS ${sql.id(name)} WITH (FORCE)`.execute(admin),
  );
}

/** Une base par fichier de test : copie de la base template déjà migrée (D-10). */
export async function createTestDatabase(): Promise<{
  db: Kysely<unknown>;
  name: string;
  drop: () => Promise<void>;
}> {
  const adminUri = inject('pgAdminUri');
  const name = uniqueName();
  await withMaintenance(adminUri, (admin) =>
    sql`CREATE DATABASE ${sql.id(name)} TEMPLATE prosperity_tpl OWNER ${sql.id(MIGRATOR_ROLE)}`.execute(
      admin,
    ),
  );
  const db = openDatabase(databaseUri(adminUri, name));
  return {
    db,
    name,
    drop: async () => {
      await db.destroy();
      await dropDatabase(adminUri, name);
    },
  };
}

/** Base vide (`TEMPLATE template0`), aucune migration : pour tester la migration elle-même. */
export async function createEmptyDatabase(): Promise<{
  admin: Kysely<unknown>;
  migrator: Kysely<unknown>;
  name: string;
  drop: () => Promise<void>;
}> {
  const adminUri = inject('pgAdminUri');
  const name = uniqueName();
  await withMaintenance(adminUri, (maintenance) =>
    sql`CREATE DATABASE ${sql.id(name)} TEMPLATE template0 OWNER ${sql.id(MIGRATOR_ROLE)}`.execute(
      maintenance,
    ),
  );
  const uri = databaseUri(adminUri, name);
  const admin = openDatabase(uri);
  const migrator = openDatabase(uri, MIGRATOR_ROLE);
  return {
    admin,
    migrator,
    name,
    drop: async () => {
      await migrator.destroy();
      await admin.destroy();
      await dropDatabase(adminUri, name);
    },
  };
}
