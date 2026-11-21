import type { Kysely } from 'kysely';
import { Migrator } from 'kysely/migration';
import { SqlFileMigrationProvider } from './sql-migration-provider.ts';

/**
 * Applique les migrations en attente de `migrationsDir` et renvoie les noms appliqués.
 * `db` doit être une connexion du rôle de migration (jamais un superutilisateur, D-10).
 * Lève une erreur qui nomme la migration en échec.
 */
export async function migrateToLatest(
  db: Kysely<unknown>,
  migrationsDir: string,
): Promise<string[]> {
  const migrator = new Migrator({ db, provider: new SqlFileMigrationProvider(migrationsDir) });
  const { error, results = [] } = await migrator.migrateToLatest();
  const failed = results.find((result) => result.status === 'Error');
  if (failed !== undefined) {
    throw new Error(`migration ${failed.migrationName} en échec`, { cause: error });
  }
  if (error !== undefined) {
    throw new Error('migrations non appliquées', { cause: error });
  }
  return results.map((result) => result.migrationName);
}
