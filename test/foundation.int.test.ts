import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { sql } from 'kysely';
import type { Kysely } from 'kysely';
import { DatabaseError } from 'pg';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { migrateToLatest } from '../src/db/migrate.ts';
import { MIGRATOR_ROLE, provisionMigrator } from '../src/db/provision.ts';
import { SqlFileMigrationProvider } from '../src/db/sql-migration-provider.ts';
import { createEmptyDatabase, createTestDatabase } from './db.ts';

const MIGRATIONS_DIR = resolve(import.meta.dirname, '..', 'db', 'migrations');
const UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** SQLSTATE de l'erreur PostgreSQL qui rejette `attempt`, `undefined` si elle réussit. */
async function sqlStateOf(attempt: Promise<unknown>): Promise<string | undefined> {
  try {
    await attempt;
    return undefined;
  } catch (error) {
    return error instanceof DatabaseError ? error.code : 'not-a-database-error';
  }
}

describe('socle base de données sur PostgreSQL 18 réel', () => {
  let db: Kysely<unknown>;
  let drop: () => Promise<void>;

  beforeAll(async () => {
    ({ db, drop } = await createTestDatabase());
  });

  afterAll(async () => {
    await drop();
  });

  it('[foundation:pg-version] le serveur est en version 18.7', async () => {
    const result = await sql<{ server_version: string }>`SHOW server_version`.execute(db);
    expect(result.rows[0]?.server_version).toMatch(/^18\.7/);
  });

  it('[foundation:uuidv7] uuidv7() natif renvoie un UUID de version 7', async () => {
    const result = await sql<{ id: string }>`SELECT uuidv7()::text AS id`.execute(db);
    expect(result.rows[0]?.id).toMatch(UUID_V7);
  });

  it('[foundation:app-role-no-ddl] le rôle app ne peut créer de table ni dans prosperity ni dans public', async () => {
    const states = await db.connection().execute(async (connection) => {
      await sql`SET ROLE prosperity_app`.execute(connection);
      try {
        return [
          await sqlStateOf(sql`CREATE TABLE prosperity.x (id int)`.execute(connection)),
          await sqlStateOf(sql`CREATE TABLE public.x (id int)`.execute(connection)),
        ];
      } finally {
        await sql`RESET ROLE`.execute(connection);
      }
    });
    expect(states[0]).toBe('42501');
    expect(states[1]).toBe('42501');
  });

  it('[foundation:migrations-run-as-migrator] le schéma et la table d’historique appartiennent au rôle de migration', async () => {
    const schema = await sql<{ owner: string }>`
      SELECT r.rolname AS owner FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
      WHERE n.nspname = 'prosperity'`.execute(db);
    const history = await sql<{ owner: string }>`
      SELECT r.rolname AS owner FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
      WHERE c.relname = 'kysely_migration'`.execute(db);
    expect(schema.rows.map((row) => row.owner)).toEqual([MIGRATOR_ROLE]);
    expect(history.rows.map((row) => row.owner)).toEqual([MIGRATOR_ROLE]);
  });

  it('[foundation:migration-recorded] la table d’historique contient 0001_foundation', async () => {
    const result = await sql<{ name: string }>`SELECT name FROM kysely_migration`.execute(db);
    expect(result.rows.map((row) => row.name)).toEqual(['0001_foundation']);
  });
});

describe('migration sur une base vide', () => {
  it('[foundation:migrate-fresh-db] provisionne, migre une base vide puis ne réapplique rien', async () => {
    const { admin, migrator, drop } = await createEmptyDatabase();
    try {
      // Rôle déjà présent dans le cluster : le provisionnement est idempotent.
      await provisionMigrator(admin);
      expect(await migrateToLatest(migrator, MIGRATIONS_DIR)).toEqual(['0001_foundation']);
      expect(await migrateToLatest(migrator, MIGRATIONS_DIR)).toEqual([]);
    } finally {
      await drop();
    }
  });

  it('[foundation:migrate-error-names-migration] une migration invalide lève une erreur qui la nomme', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'prosperity-migrations-'));
    const { migrator, drop } = await createEmptyDatabase();
    try {
      await writeFile(join(dir, '0001_ok.sql'), 'SELECT 1;');
      await writeFile(join(dir, '0002_broken.sql'), 'THIS IS NOT SQL;');
      await writeFile(join(dir, 'README.txt'), 'ignoré : pas un fichier .sql');
      const migrations = await new SqlFileMigrationProvider(dir).getMigrations();
      expect(Object.keys(migrations)).toEqual(['0001_ok', '0002_broken']);
      await expect(migrateToLatest(migrator, dir)).rejects.toThrow('0002_broken');
    } finally {
      await drop();
      await rm(dir, { recursive: true, force: true });
    }
  });
});
