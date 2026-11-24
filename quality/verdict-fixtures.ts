import type { CheckResult } from './gate-report.ts';
import type { ApprovalsReport, VerdictTarget } from './verdict.ts';

export const SHA = 'a'.repeat(40);
export const GATE_PATH = '.github/workflows/quality.yml';

export function target(over: Partial<VerdictTarget> = {}): VerdictTarget {
  return {
    headSha: SHA,
    pr: 12,
    gateConclusion: 'success',
    gateEvent: 'pull_request',
    gatePath: GATE_PATH,
    runUrl: 'https://github.com/o/r/actions/runs/1',
    ...over,
  };
}

export function check(id: string, over: Partial<CheckResult> = {}): CheckResult {
  return {
    check: id,
    tool: id,
    version: 'v26',
    severity: 'blocking',
    passed: true,
    status: 'passed',
    issues: [],
    duration_ms: 1,
    ...over,
  };
}

export function approvals(over: Partial<ApprovalsReport> = {}): ApprovalsReport {
  return {
    approved: [],
    rejected: [],
    bootstrap: false,
    verifier: 'github-label-events@1',
    approval: null,
    ...over,
  };
}

export function harness(
  over: {
    judge?: (name: string) => unknown;
    extract?: () => Promise<string>;
    collect?: () => Promise<void>;
    target?: VerdictTarget;
  } = {},
) {
  const calls: { name: string; args: readonly string[] }[] = [];
  const collected: { target: VerdictTarget; out: string }[] = [];
  const published: { sha: string; state: string }[] = [];
  const reports: Record<string, unknown> = {
    approvals: approvals(),
    integrity: check('integrity'),
    deps: check('deps'),
  };
  return {
    calls,
    collected,
    published,
    deps: {
      target: over.target ?? target(),
      baseDir: '/base',
      workDir: '/work',
      extractHead: over.extract ?? (() => Promise.resolve('/work/head')),
      collectEvidence: (t: VerdictTarget, out: string) => {
        collected.push({ target: t, out });
        return over.collect?.() ?? Promise.resolve();
      },
      judge: (name: 'approvals' | 'integrity' | 'deps', args: readonly string[]) => {
        calls.push({ name, args });
        const result = over.judge?.(name) ?? reports[name];
        return result instanceof Error ? Promise.reject(result) : Promise.resolve(result);
      },
      publish: (sha: string, body: { state: string }) => {
        published.push({ sha, state: body.state });
        return Promise.resolve();
      },
    },
  };
}
