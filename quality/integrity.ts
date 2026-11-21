import type { CheckResult } from './gate-report.ts';

export interface IntegrityInput {
  baseDir: string;
  headDir: string;
  approvedKinds: readonly string[];
  bootstrap: boolean;
}

export function evaluateIntegrity(_input: IntegrityInput): Promise<CheckResult> {
  return Promise.resolve({
    check: 'integrity',
    tool: 'integrity',
    version: '1',
    severity: 'blocking',
    passed: true,
    status: 'passed',
    issues: [],
    duration_ms: 0,
  });
}
