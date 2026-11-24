import { join } from 'node:path';
import { buildResult, failedResult, toolErrorIssue, versionMismatchIssue } from '../check-kit.ts';
import type { CheckMeta } from '../check-kit.ts';
import type { CheckContext, CheckDefinition, CheckResult, Issue } from '../gate-report.ts';
import { isRecord, runTool, verifyNpmToolVersion } from '../tools.ts';

const META: CheckMeta = { id: 'arch', tool: 'dependency-cruiser', severity: 'blocking' };

interface Parsed {
  issues: Issue[];
  errorCount: number;
}

function violationIssue(entry: unknown): Issue | undefined {
  if (!isRecord(entry) || !isRecord(entry['rule'])) {
    return undefined;
  }
  const rule = entry['rule'];
  const from = typeof entry['from'] === 'string' ? entry['from'] : '';
  const to = typeof entry['to'] === 'string' ? entry['to'] : '';
  return {
    rule: typeof rule['name'] === 'string' ? rule['name'] : 'dependency-cruiser',
    message: to === '' ? from : `${from} → ${to}`,
    file: from,
  };
}

/**
 * Sortie `--output-type json` : le code de sortie vaut 0 même avec des violations
 * (Pitfall 3). Le verdict se lit dans `summary.error` et `summary.violations`.
 */
function parseDepcruiseOutput(stdout: string): Parsed | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  if (!isRecord(parsed) || !isRecord(parsed['summary'])) {
    return undefined;
  }
  const summary = parsed['summary'];
  const errorCount = summary['error'];
  const violations: unknown = summary['violations'];
  if (typeof errorCount !== 'number' || !Array.isArray(violations)) {
    return undefined;
  }
  const entries: unknown[] = violations;
  const issues: Issue[] = [];
  for (const entry of entries) {
    const issue = violationIssue(entry);
    if (issue === undefined) {
      return undefined;
    }
    issues.push(issue);
  }
  return { issues, errorCount };
}

async function run(ctx: CheckContext): Promise<CheckResult> {
  const start = Date.now();
  const version = await verifyNpmToolVersion(ctx.root, 'dependency-cruiser');
  if (!version.ok) {
    return failedResult(
      META,
      version.found,
      versionMismatchIssue('dependency-cruiser', version.found, version.expected),
      start,
    );
  }
  const depcruise = await runTool({
    command: join(ctx.root, 'node_modules', '.bin', 'depcruise'),
    args: ['src', '--config', '.dependency-cruiser.cjs', '--output-type', 'json'],
    cwd: ctx.root,
    timeoutMs: 300_000,
  });
  const parsed = depcruise.code === 0 ? parseDepcruiseOutput(depcruise.stdout) : undefined;
  // Une violation sans entrée lisible ne conclut jamais « passé ».
  if (parsed === undefined || (parsed.errorCount > 0 && parsed.issues.length === 0)) {
    return failedResult(
      META,
      version.found,
      toolErrorIssue('depcruise', depcruise.code, depcruise.stderr),
      start,
    );
  }
  return buildResult(
    META,
    {
      status: parsed.errorCount > 0 ? 'failed' : 'passed',
      version: version.found,
      issues: parsed.issues,
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
