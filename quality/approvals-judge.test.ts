import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { APPROVAL_KINDS, judgeApprovals, loadApproversConfig, VERIFIER } from './approvals.ts';
import {
  CONFIG,
  DEPS,
  evidence,
  GATE,
  labelEvent,
  SHA,
  writeConfig,
} from './approvals-fixtures.ts';
import { readApprovalsReport } from './verdict-rules.ts';

let scratch = '';

beforeEach(async () => {
  scratch = await mkdtemp(join(tmpdir(), 'approvals-judge-test-'));
});

afterEach(async () => {
  await rm(scratch, { recursive: true, force: true });
});

// --- Configuration lue dans la base -----------------------------------------

describe('loadApproversConfig', () => {
  it('lit <base>/quality/approvers.json', async () => {
    await writeConfig(scratch, CONFIG);
    expect(await loadApproversConfig(scratch)).toEqual(CONFIG);
  });

  it('rend undefined quand le fichier manque', async () => {
    expect(await loadApproversConfig(scratch)).toBeUndefined();
  });

  it.each([
    ['allowlist vide', { allowlist: [], labels: [DEPS] }],
    ['labels vide', { allowlist: ['sebc-dev'], labels: [] }],
    ['allowlist avec une chaîne vide', { allowlist: [''], labels: [DEPS] }],
    ['labels de mauvais type', { allowlist: ['sebc-dev'], labels: 'x' }],
    ['pas un objet', ['sebc-dev']],
  ])('rend undefined pour une configuration invalide : %s', async (_name, content) => {
    await writeConfig(scratch, content);
    expect(await loadApproversConfig(scratch)).toBeUndefined();
  });

  it('rend undefined pour un JSON illisible', async () => {
    await mkdir(join(scratch, 'quality'));
    await writeFile(join(scratch, 'quality', 'approvers.json'), '{pas du json');
    expect(await loadApproversConfig(scratch)).toBeUndefined();
  });
});

async function base(content: unknown = CONFIG): Promise<string> {
  const dir = join(scratch, 'base');
  await writeConfig(dir, content);
  return dir;
}
// --- judgeApprovals ---------------------------------------------------------

const judge = (baseDir: string, e: unknown, over: { bootstrap?: boolean; pr?: number } = {}) =>
  judgeApprovals({
    baseDir,
    headSha: SHA,
    pr: over.pr ?? 300,
    evidence: e,
    bootstrap: over.bootstrap ?? false,
  });

describe('judgeApprovals', () => {
  it('rend un rapport approuvé relu à l identique par readApprovalsReport', async () => {
    const report = await judge(await base(), evidence({ labelEvents: [labelEvent()] }));
    expect(report).toMatchObject({ approved: [DEPS], bootstrap: false, verifier: VERIFIER });
    expect(readApprovalsReport(JSON.parse(JSON.stringify(report)))).toEqual(report);
  });

  it('rend un rapport de refus relu à l identique par readApprovalsReport', async () => {
    const report = await judge(await base(), evidence());
    expect(report.approval).toBeNull();
    expect(report.rejected).toHaveLength(2);
    expect(readApprovalsReport(JSON.parse(JSON.stringify(report)))).toEqual(report);
  });

  it('la configuration de la base l emporte sur celle d un dossier « tête » permissif', async () => {
    const baseDir = await base();
    const head = join(scratch, 'head');
    await writeConfig(head, { allowlist: ['github-actions[bot]'], labels: [DEPS] });
    const labelEvents = [labelEvent({ actor: 'github-actions[bot]' })];
    const report = await judge(baseDir, evidence({ labelEvents }));
    expect(report.approved).toEqual([]);
    expect(report.rejected).toContainEqual({ kind: DEPS, reason: 'approval-actor-not-allowed' });
  });

  it('refuse chaque sorte avec approvers-config-missing quand la base n a pas de configuration', async () => {
    const report = await judge(scratch, evidence({ labelEvents: [labelEvent()] }));
    expect(report).toMatchObject({ approved: [], bootstrap: false, approval: null });
    expect(report.rejected).toEqual(
      APPROVAL_KINDS.map((kind) => ({ kind, reason: 'approvers-config-missing' })),
    );
  });

  it('en amorçage, l allowlist est le propriétaire du dépôt de base et le rapport porte bootstrap', async () => {
    const labelEvents = [
      labelEvent({ actor: 'o' }),
      labelEvent({ id: 2, label: GATE, actor: 'sebc-dev' }),
    ];
    const report = await judge(scratch, evidence({ labelEvents }), { bootstrap: true });
    expect(report).toMatchObject({ approved: [DEPS], bootstrap: true, verifier: VERIFIER });
    expect(report.rejected).toEqual([{ kind: GATE, reason: 'approval-actor-not-allowed' }]);
    expect(readApprovalsReport(JSON.parse(JSON.stringify(report)))).toEqual(report);
  });

  it.each([
    ['illisibles', 'pas des preuves'],
    ['absentes', undefined],
    ['d une autre PR', { ...evidence(), pr: 301, pull: { ...evidence().pull, number: 301 } }],
    ['d un autre SHA', { ...evidence(), headSha: 'b'.repeat(40) }],
  ])('refuse chaque sorte avec approval-evidence-invalid pour des preuves %s', async (_name, e) => {
    const report = await judge(await base(), e);
    expect(report.approved).toEqual([]);
    expect(report.rejected).toEqual(
      APPROVAL_KINDS.map((kind) => ({ kind, reason: 'approval-evidence-invalid' })),
    );
  });

  it('refuse en amorçage des preuves illisibles', async () => {
    const report = await judge(scratch, 'x', { bootstrap: true });
    expect(report).toMatchObject({ approved: [], bootstrap: true });
    expect(report.rejected.map((r) => r.reason)).toEqual(
      APPROVAL_KINDS.map(() => 'approval-evidence-invalid'),
    );
  });
});
