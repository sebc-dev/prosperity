import { resolve } from 'node:path';
import { isProtected, loadProtectedPaths } from '../protected-paths.ts';
import { runTool } from '../tools.ts';

// Couche 3 de D-04 : refuse un commit qui touche un chemin protégé sans la variable
// d'autorisation humaine. Branché au pré-commit lefthook au plan 01-14 (D-01) ; tant
// qu'il n'est pas branché, ce script ne s'exécute pas.

const HUMAN_VARIABLE = 'PROSPERITY_HUMAN_GATE_EDIT';
const EXIT_REFUSED = 1;
const EXIT_ERROR = 2;

async function stagedProtected(): Promise<string[]> {
  const { paths, agentExempt } = await loadProtectedPaths(resolve(import.meta.dirname, '..', '..'));
  const globs = paths.filter((glob) => !agentExempt.includes(glob));
  const staged = await runTool({
    command: 'git',
    // --no-renames : un renommage hors d'un chemin protégé apparaît aussi sous son ancien chemin.
    args: ['diff', '--cached', '--name-only', '--no-renames', '--diff-filter=ACMRD', '-z'],
    cwd: process.cwd(),
    timeoutMs: 30_000,
  });
  if (staged.code !== 0) {
    throw new Error(`git diff --cached a échoué : ${staged.stderr.trim()}`);
  }
  return staged.stdout.split('\0').filter((file) => file !== '' && isProtected(file, globs));
}

async function main(): Promise<number> {
  const files = await stagedProtected();
  if (files.length === 0 || process.env[HUMAN_VARIABLE] === '1') {
    return 0;
  }
  process.stderr.write(
    [
      'Commit refusé : il touche des chemins protégés de la gate.',
      ...files.map((file) => `  - ${file}`),
      `commit humain : ${HUMAN_VARIABLE}=1 git commit …`,
      '',
    ].join('\n'),
  );
  return EXIT_REFUSED;
}

if (import.meta.main) {
  try {
    process.exitCode = await main();
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
    process.exitCode = EXIT_ERROR;
  }
}
