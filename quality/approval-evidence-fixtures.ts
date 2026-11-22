import { chmod, mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { ApprovalEvidence } from './approval-evidence.ts';

export const SHA = 'a'.repeat(40);
export const OTHER_SHA = 'b'.repeat(40);
export const IDS = { repository: 'o/r', pr: 300, headSha: SHA };

// --- Fixtures à la forme réelle de l'API GitHub -----------------------------

export const PULL = {
  number: 300,
  head: { sha: SHA, ref: 'feat/x', repo: { full_name: 'o/r' } },
  base: { repo: { owner: { login: 'o' } } },
  labels: [{ name: 'deps-approved' }, { name: 'bug' }],
};

export const EVENT_PAGES = [
  [
    {
      id: 11,
      event: 'labeled',
      actor: { login: 'sebc-dev' },
      label: { name: 'deps-approved' },
      created_at: '2026-11-22T10:05:00Z',
    },
    { id: 12, event: 'commented', created_at: '2026-11-22T10:06:00Z' },
    { id: 13, event: 'assigned' },
  ],
  [
    {
      id: 14,
      event: 'unlabeled',
      actor: null,
      label: { name: 'deps-approved' },
      created_at: '2026-11-22T10:07:00Z',
    },
    { id: 15, event: 'head_ref_force_pushed', created_at: '2026-11-22T10:08:00Z' },
  ],
];

export const RUN_PAGES = [
  {
    total_count: 2,
    workflow_runs: [
      {
        created_at: '2026-11-22T10:01:00Z',
        head_sha: SHA,
        event: 'pull_request',
        head_branch: 'feat/x',
        head_repository: { full_name: 'o/r' },
      },
    ],
  },
  {
    total_count: 2,
    workflow_runs: [
      {
        created_at: '2026-11-22T10:02:00Z',
        head_sha: OTHER_SHA,
        event: 'pull_request',
        head_branch: null,
        head_repository: null,
      },
    ],
  },
];

export const EXPECTED: ApprovalEvidence = {
  repository: 'o/r',
  pr: 300,
  headSha: SHA,
  pull: {
    number: 300,
    headSha: SHA,
    headRef: 'feat/x',
    headRepository: 'o/r',
    baseOwner: 'o',
    labels: ['deps-approved', 'bug'],
  },
  labelEvents: [
    {
      id: 11,
      event: 'labeled',
      actor: 'sebc-dev',
      label: 'deps-approved',
      createdAt: '2026-11-22T10:05:00Z',
    },
    {
      id: 14,
      event: 'unlabeled',
      actor: '',
      label: 'deps-approved',
      createdAt: '2026-11-22T10:07:00Z',
    },
  ],
  forcePushes: ['2026-11-22T10:08:00Z'],
  runs: [
    {
      createdAt: '2026-11-22T10:01:00Z',
      headSha: SHA,
      event: 'pull_request',
      headBranch: 'feat/x',
      headRepository: 'o/r',
    },
    {
      createdAt: '2026-11-22T10:02:00Z',
      headSha: OTHER_SHA,
      event: 'pull_request',
      headBranch: '',
      headRepository: '',
    },
  ],
};

export const raw = (over: Partial<Record<'pull' | 'eventPages' | 'runPages', unknown>> = {}) => ({
  pull: PULL,
  eventPages: EVENT_PAGES,
  runPages: RUN_PAGES,
  ...over,
});

// --- Faux `gh` ---------------------------------------------------------------

export interface Fixtures {
  pull?: unknown;
  events?: unknown;
  runs?: unknown;
}

/** Faux `gh` : consigne arguments et jetons de chaque appel, rend une fixture selon le chemin demandé. */
export async function fakeGh(scratch: string, fixtures: Fixtures = {}): Promise<NodeJS.ProcessEnv> {
  const bin = join(scratch, 'bin');
  await mkdir(bin);
  const script = [
    '#!/bin/sh',
    '{ printf "%s\\n" "$@"; printf "%s\\n" "--END--"; } >> "$FAKE_LOG"',
    'printf "%s|%s|%s\\n" "${GH_TOKEN-unset}" "${GATE_STATUS_TOKEN-unset}" "${GITHUB_TOKEN-unset}" >> "$FAKE_ENV"',
    'case "$*" in',
    '  *actions/runs*) cat "$FAKE_RUNS" ;;',
    '  *issues/*/events*) cat "$FAKE_EVENTS" ;;',
    '  *pulls/*) cat "$FAKE_PULL" ;;',
    'esac',
    'exit "${FAKE_EXIT:-0}"',
    '',
  ].join('\n');
  await writeFile(join(bin, 'gh'), script);
  await chmod(join(bin, 'gh'), 0o755);
  const given = { pull: PULL, events: EVENT_PAGES, runs: RUN_PAGES, ...fixtures };
  const serialize = (value: unknown): string =>
    typeof value === 'string' ? value : JSON.stringify(value);
  await writeFile(join(scratch, 'pull.json'), serialize(given.pull));
  await writeFile(join(scratch, 'events.json'), serialize(given.events));
  await writeFile(join(scratch, 'runs.json'), serialize(given.runs));
  return {
    PATH: `${bin}:${process.env['PATH'] ?? ''}`,
    FAKE_LOG: join(scratch, 'calls.log'),
    FAKE_ENV: join(scratch, 'env.log'),
    FAKE_PULL: join(scratch, 'pull.json'),
    FAKE_EVENTS: join(scratch, 'events.json'),
    FAKE_RUNS: join(scratch, 'runs.json'),
  };
}
