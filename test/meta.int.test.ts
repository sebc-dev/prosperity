import { sql } from 'kysely';
import type { Kysely } from 'kysely';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { MIGRATOR_ROLE } from '../src/db/provision.ts';
import { createTestDatabase } from './db.ts';

const APP_ROLE = 'prosperity_app';

interface RoleFlags {
  rolsuper: boolean;
  rolbypassrls: boolean;
  rolcreatedb: boolean;
  rolcreaterole: boolean;
  rolcanlogin: boolean;
}

async function roleFlags(db: Kysely<unknown>, role: string): Promise<RoleFlags | undefined> {
  const result = await sql<RoleFlags>`
    SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolcanlogin
    FROM pg_roles WHERE rolname = ${role}`.execute(db);
  return result.rows[0];
}

/** Tables ordinaires qui ont une colonne `owner_member_id` sans RLS active. */
async function rlsOffenders(db: Kysely<unknown>): Promise<string[]> {
  const result = await sql<{ table_name: string }>`
      SELECT n.nspname || '.' || c.relname AS table_name
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid
      WHERE c.relkind IN ('r', 'p')
        AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
        AND a.attname = 'owner_member_id' AND NOT a.attisdropped
        AND NOT c.relrowsecurity
      ORDER BY 1`.execute(db);
  return result.rows.map((row) => row.table_name);
}

// Méta-tests du cloisonnement (D-10) : joués sur une base qui a reçu toutes les migrations du
// dépôt, ils s'appliquent à toute table future sans qu'on ait à y penser.
describe('méta-tests du cloisonnement sur PostgreSQL 18 réel', () => {
  let db: Kysely<unknown>;
  let drop: () => Promise<void>;

  beforeAll(async () => {
    ({ db, drop } = await createTestDatabase());
  });

  afterAll(async () => {
    await drop();
  });

  it('[meta:rls-owner-member-id] toute table à owner_member_id a la RLS active', async () => {
    const offenders = await rlsOffenders(db);
    expect(offenders, `tables à owner_member_id sans RLS : ${offenders.join(', ')}`).toEqual([]);
  });

  it('[meta:app-role-no-ddl] le rôle app ne crée rien, ne possède rien et n’a aucun privilège élevé', async () => {
    const creatable = await sql<{ nspname: string }>`
      SELECT nspname FROM pg_namespace
      WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
        AND has_schema_privilege(${APP_ROLE}, nspname, 'CREATE')`.execute(db);
    const ownedSchemas = await sql<{ nspname: string }>`
      SELECT n.nspname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
      WHERE r.rolname = ${APP_ROLE}`.execute(db);
    const ownedRelations = await sql<{ relname: string }>`
      SELECT c.relname FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
      WHERE r.rolname = ${APP_ROLE}`.execute(db);
    expect(creatable.rows).toEqual([]);
    expect(ownedSchemas.rows).toEqual([]);
    expect(ownedRelations.rows).toEqual([]);
    expect(await roleFlags(db, APP_ROLE)).toEqual({
      rolsuper: false,
      rolbypassrls: false,
      rolcreatedb: false,
      rolcreaterole: false,
      rolcanlogin: false,
    });
  });

  it('[meta:migrator-role] le rôle de migration est borné, séparé du rôle app et propriétaire du schéma', async () => {
    const flags = await roleFlags(db, MIGRATOR_ROLE);
    expect(flags?.rolsuper).toBe(false);
    expect(flags?.rolbypassrls).toBe(false);
    expect(flags?.rolcreatedb).toBe(false);
    const membership = await sql<{ member: boolean }>`
      SELECT pg_has_role(${APP_ROLE}, ${MIGRATOR_ROLE}, 'MEMBER') AS member`.execute(db);
    expect(membership.rows[0]?.member).toBe(false);
    // Une future migration jouée par un autre rôle crée des objets qui ne lui appartiennent pas.
    const foreign = await sql<{ relname: string; owner: string }>`
      SELECT c.relname, r.rolname AS owner
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_roles r ON r.oid = c.relowner
      WHERE n.nspname = 'prosperity' AND r.rolname <> ${MIGRATOR_ROLE}`.execute(db);
    expect(foreign.rows).toEqual([]);
  });
});
