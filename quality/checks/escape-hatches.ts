import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import { compareToBaseline, countEscapeHatches, isCountedPath } from '../escape-hatches.ts';
import type { CheckContext, CheckDefinition, CheckResult } from '../gate-report.ts';
import { isRecord, readJsonRecord, runTool } from '../tools.ts';

const META: CheckMeta = { id: 'escape-hatches', tool: 'escape-hatches', severity: 'blocking' };
const FALLBACK_VERSION = '0.0.0';

/** Budget lu dans `quality/baseline.json` : `{ escapeHatches: { <motif>: <n> } }`. */
async function readBaseline(root: string): Promise<Record<string, number>> {
  const parsed = await readJsonRecord(join(root, 'quality', 'baseline.json'));
  const table = parsed['escapeHatches'];
  const baseline: Record<string, number> = {};
  if (isRecord(table)) {
    for (const [pattern, value] of Object.entries(table)) {
      if (typeof value === 'number') {
        baseline[pattern] = value;
      }
    }
  }
  return baseline;
}

async function readVersion(root: string): Promise<string> {
  const manifest = await readJsonRecord(join(root, 'package.json'));
  const version = manifest['version'];
  return typeof version === 'string' ? version : FALLBACK_VERSION;
}

/** Fichiers suivis et non suivis non ignorés (Pitfall 11) : le worktree d'auto-test est vu. */
async function listFiles(root: string): Promise<string[] | undefined> {
  const listed = await runTool({
    command: 'git',
    args: ['ls-files', '-z', '--cached', '--others', '--exclude-standard'],
    cwd: root,
    timeoutMs: 30_000,
  });
  if (listed.code !== 0) {
    return undefined;
  }
  return listed.stdout.split('\0').filter((path) => path !== '' && isCountedPath(path));
}

async function readContent(
  root: string,
  path: string,
): Promise<{ path: string; content: string }[]> {
  try {
    return [{ path, content: await readFile(join(root, path), 'utf8') }];
  } catch {
    // Fichier suivi mais supprimé du worktree : rien à compter.
    return [];
  }
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await readVersion(ctx.root);
  const paths = await listFiles(ctx.root);
  if (paths === undefined) {
    return failedResult(
      META,
      version,
      toolErrorIssue('git ls-files', 1, 'liste des fichiers illisible'),
      start,
    );
  }
  const files = (await Promise.all(paths.map((path) => readContent(ctx.root, path)))).flat();
  const { violations, notes } = compareToBaseline(
    countEscapeHatches(files),
    await readBaseline(ctx.root),
  );
  return buildResult(
    META,
    {
      status: violations.length > 0 ? 'failed' : 'passed',
      version,
      issues: violations,
      ...(notes.length > 0 ? { note: notes.join(' ; ') } : {}),
    },
    start,
  );
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'run',
  run,
};
