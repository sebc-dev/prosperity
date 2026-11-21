import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { runTool, verifyNpmToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'typecheck', tool: 'tsc', severity: 'blocking' };
const NORMAL_CODES = new Set([0, 1, 2]);
// `chemin(ligne,col): error TSnnnn: message` ; les erreurs globales n'ont pas de position.
const TSC_ERROR = /^(?:(.+?)\((\d+),\d+\): )?error (TS\d+): (.*)$/;

function parseTscOutput(stdout: string): Issue[] {
  const issues: Issue[] = [];
  for (const line of stdout.split(/\r?\n/)) {
    const match = TSC_ERROR.exec(line);
    const rule = match?.[3];
    if (rule === undefined) {
      continue;
    }
    const issue: Issue = { rule, message: match?.[4] ?? '' };
    const file = match?.[1];
    const lineNumber = match?.[2];
    if (file !== undefined) {
      issue.file = file;
    }
    if (lineNumber !== undefined) {
      issue.line = Number(lineNumber);
    }
    issues.push(issue);
  }
  return issues;
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'typescript');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('typescript', version.found, version.expected),
      start,
    );
  }
  const tsc = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'tsc'),
    args: ['--noEmit', '-p', 'tsconfig.json', '--pretty', 'false'],
    cwd: ctx.root,
    timeoutMs: 120_000,
  });
  const issues = NORMAL_CODES.has(tsc.code) ? parseTscOutput(tsc.stdout) : [];
  // Un code non nul sans erreur lisible ne peut jamais valoir « passé ».
  if (tsc.code !== 0 && issues.length === 0) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('tsc', tsc.code, tsc.stderr || tsc.stdout),
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
