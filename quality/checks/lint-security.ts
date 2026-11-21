import { join, relative } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runTool, verifyNpmToolVersion } from '../tools.ts';

// Advisory : eslint-plugin-security est bruyant (CLAUDE.md §10.2), il n'influe jamais sur le verdict.
const META: CheckMeta = { id: 'lint-security', tool: 'eslint', severity: 'advisory' };
const NORMAL_CODES = new Set([0, 1]);

function messageIssue(root: string, filePath: string, message: unknown): Issue | undefined {
  if (!isRecord(message)) {
    return undefined;
  }
  const issue: Issue = {
    rule: typeof message['ruleId'] === 'string' ? message['ruleId'] : 'eslint',
    message: typeof message['message'] === 'string' ? message['message'] : '',
    file: relative(root, filePath),
  };
  if (typeof message['line'] === 'number') {
    issue.line = message['line'];
  }
  return issue;
}

/** Sortie `--format json` : un tableau de `{ filePath, messages }` ; un message = une issue. */
function parseEslintOutput(root: string, stdout: string): Issue[] | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  if (!Array.isArray(parsed)) {
    return undefined;
  }
  const issues: Issue[] = [];
  const entries: unknown[] = parsed;
  for (const entry of entries) {
    if (
      !isRecord(entry) ||
      typeof entry['filePath'] !== 'string' ||
      !Array.isArray(entry['messages'])
    ) {
      return undefined;
    }
    const filePath = entry['filePath'];
    const messages: unknown[] = entry['messages'];
    for (const message of messages) {
      const issue = messageIssue(root, filePath, message);
      if (issue !== undefined) {
        issues.push(issue);
      }
    }
  }
  return issues;
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'eslint-plugin-security');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('eslint-plugin-security', version.found, version.expected),
      start,
    );
  }
  const eslint = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'eslint'),
    args: ['--config', 'eslint.security.config.mjs', '--format', 'json', '.'],
    cwd: ctx.root,
    timeoutMs: 300_000,
  });
  const issues = NORMAL_CODES.has(eslint.code)
    ? parseEslintOutput(ctx.root, eslint.stdout)
    : undefined;
  if (issues === undefined) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('eslint', eslint.code, eslint.stderr),
      start,
    );
  }
  return buildResult(
    META,
    {
      status: issues.length === 0 ? 'passed' : 'failed',
      version: version.found,
      issues,
      note: 'advisory : eslint-plugin-security, passe séparée',
    },
    start,
  );
}

export const check: CheckDefinition = {
  id: META.id,
  tool: META.tool,
  severity: META.severity,
  push: 'skip-ci-only',
  run,
};
