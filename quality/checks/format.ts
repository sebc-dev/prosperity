import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runTool, verifyNpmToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'format', tool: 'biome', severity: 'blocking' };
const NORMAL_CODES = new Set([0, 1]);

function diagnosticPath(location: unknown): string | undefined {
  if (!isRecord(location)) {
    return undefined;
  }
  const path = location['path'];
  if (typeof path === 'string') {
    return path;
  }
  return isRecord(path) && typeof path['file'] === 'string' ? path['file'] : undefined;
}

function issueHead(diagnostic: Record<string, unknown>): Pick<Issue, 'rule' | 'message'> {
  const category = diagnostic['category'];
  if (category === 'format') {
    return { rule: 'format', message: 'fichier non conforme au format Biome' };
  }
  const message = diagnostic['message'];
  return {
    rule: typeof category === 'string' ? category : 'biome',
    message: typeof message === 'string' ? message : '',
  };
}

function toIssue(diagnostic: unknown): Issue | undefined {
  if (!isRecord(diagnostic) || diagnostic['severity'] !== 'error') {
    return undefined;
  }
  const issue: Issue = issueHead(diagnostic);
  const file = diagnosticPath(diagnostic['location']);
  if (file !== undefined) {
    issue.file = file;
  }
  return issue;
}

/** Sortie `--reporter=json` : `{ diagnostics: [...] }` ; `undefined` si illisible. */
function parseBiomeOutput(stdout: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  const diagnostics = isRecord(parsed) ? parsed['diagnostics'] : undefined;
  if (!Array.isArray(diagnostics)) {
    return undefined;
  }
  return diagnostics.flatMap((entry: unknown) => toIssue(entry) ?? []);
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, '@biomejs/biome');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('@biomejs/biome', version.found, version.expected),
      start,
    );
  }
  // Mode vérification : sans `--write`, Biome n'écrit rien.
  const biome = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'biome'),
    args: ['format', '--reporter=json'],
    cwd: ctx.root,
    timeoutMs: 120_000,
  });
  const issues = NORMAL_CODES.has(biome.code) ? parseBiomeOutput(biome.stdout) : undefined;
  if (issues === undefined) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('biome', biome.code, biome.stderr),
      start,
    );
  }
  // Un code 1 sans diagnostic lisible ne peut pas valoir « passé ».
  if (biome.code === 1 && issues.length === 0) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('biome', biome.code, 'code 1 sans diagnostic'),
      start,
    );
  }
  return buildResult(
    META,
    { status: issues.length === 0 ? 'passed' : 'failed', version: version.found, issues },
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
