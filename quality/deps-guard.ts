import type { CheckResult } from './gate-report.ts';

export interface DepChange {
  name: string;
  from?: string;
  to?: string;
  kind: 'dependency-added' | 'dependency-changed' | 'dependency-removed' | 'transitive-added';
}

export interface DependencySnapshot {
  packageJson: string;
  lockfile: string;
}

export type RegistryLookup = (name: string) => Promise<{ exists: boolean; createdAt?: string }>;

// Squelette RED : signatures finales, comportement volontairement faux.
export function diffDependencies(_base: DependencySnapshot, _head: DependencySnapshot): DepChange[] {
  return [{ name: '?', kind: 'dependency-removed' }];
}

export function evaluateDependencies(
  _changes: readonly DepChange[],
  _opts: {
    approvedKinds: readonly string[];
    minAgeDays: number;
    now: Date;
    lookup: RegistryLookup;
  },
): Promise<CheckResult> {
  return Promise.resolve({
    check: '?',
    tool: '?',
    version: '',
    severity: 'advisory',
    passed: true,
    status: 'passed',
    issues: [],
    duration_ms: 0,
  });
}

export function runDepsGuardCli(
  _argv: readonly string[],
  _io: { lookup: RegistryLookup; now: Date; minAgeDays: number },
): Promise<number> {
  return Promise.resolve(99);
}
