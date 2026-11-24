import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { sql } from 'kysely';
import type { Kysely } from 'kysely';
import type { Migration, MigrationProvider } from 'kysely/migration';

const SQL_SUFFIX = '.sql';

/**
 * Fournisseur de migrations Kysely lisant des fichiers `.sql` forward-only :
 * clé = nom de fichier sans `.sql`, ordre lexical, aucun `down`.
 */
export class SqlFileMigrationProvider implements MigrationProvider {
  readonly #dir: string;

  constructor(dir: string) {
    this.#dir = dir;
  }

  async getMigrations(): Promise<Record<string, Migration>> {
    const files = (await readdir(this.#dir))
      .filter((file) => file.endsWith(SQL_SUFFIX))
      .sort((a, b) => a.localeCompare(b));
    const migrations: Record<string, Migration> = {};
    for (const file of files) {
      const text = await readFile(join(this.#dir, file), 'utf8');
      migrations[file.slice(0, -SQL_SUFFIX.length)] = {
        up: async (db: Kysely<unknown>): Promise<void> => {
          await sql.raw(text).execute(db);
        },
      };
    }
    return migrations;
  }
}
