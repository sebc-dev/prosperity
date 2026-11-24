import { describe, expect, it } from 'vitest';
import { evidenceFromApi, parseApprovalEvidence } from './approval-evidence.ts';
import { EXPECTED, IDS, PULL, raw, SHA } from './approval-evidence-fixtures.ts';

describe('evidenceFromApi', () => {
  it('normalise les pages de --slurp : événements de label et de push forcé gardés, autres ignorés', () => {
    expect(evidenceFromApi(raw(), IDS)).toEqual(EXPECTED);
  });

  it('range un acteur null en chaîne vide', () => {
    expect(evidenceFromApi(raw(), IDS)?.labelEvents[1]?.actor).toBe('');
  });

  it.each([
    ['pull absent', raw({ pull: undefined })],
    ['pull sans head.sha', raw({ pull: { ...PULL, head: { ...PULL.head, sha: 1 } } })],
    ['pull sans dépôt de tête', raw({ pull: { ...PULL, head: { ...PULL.head, repo: null } } })],
    ['pull d une autre PR', raw({ pull: { ...PULL, number: 301 } })],
    ['labels mal formés', raw({ pull: { ...PULL, labels: [{ nom: 'x' }] } })],
    ['pages d événements non tableau', raw({ eventPages: { 0: [] } })],
    ['page d événements non tableau', raw({ eventPages: [{}] })],
    [
      'labeled sans date',
      raw({ eventPages: [[{ id: 1, event: 'labeled', label: { name: 'x' }, actor: null }]] }),
    ],
    [
      'labeled sans label',
      raw({ eventPages: [[{ id: 1, event: 'labeled', actor: null, created_at: 'x' }]] }),
    ],
    ['page de runs sans workflow_runs', raw({ runPages: [{ total_count: 0 }] })],
    ['pages de runs non tableau', raw({ runPages: 'x' })],
    [
      'run sans date',
      raw({ runPages: [{ workflow_runs: [{ head_sha: SHA, event: 'pull_request' }] }] }),
    ],
  ])('rend undefined pour une réponse hors forme : %s', (_name, input) => {
    expect(evidenceFromApi(input, IDS)).toBeUndefined();
  });
});

describe('parseApprovalEvidence', () => {
  it('relit à l identique un fichier écrit par le collecteur', () => {
    expect(parseApprovalEvidence(JSON.parse(JSON.stringify(EXPECTED)))).toEqual(EXPECTED);
  });

  const broken = (patch: Record<string, unknown>): unknown => ({ ...EXPECTED, ...patch });
  it.each([
    ['pas un objet', 'preuves'],
    ['SHA de 39 caractères', broken({ headSha: SHA.slice(1) })],
    ['SHA de tête de la PR invalide', broken({ pull: { ...EXPECTED.pull, headSha: 'XYZ' } })],
    ['numéro de PR non entier', broken({ pr: 1.5 })],
    ['numéro de PR nul', broken({ pr: 0 })],
    ['dépôt absent', broken({ repository: undefined })],
    [
      'date de label illisible',
      broken({ labelEvents: [{ ...EXPECTED.labelEvents[0], createdAt: 'hier' }] }),
    ],
    [
      'type d événement de label inconnu',
      broken({ labelEvents: [{ ...EXPECTED.labelEvents[0], event: 'commented' }] }),
    ],
    ['événements absents', broken({ labelEvents: undefined })],
    ['pushs forcés absents', broken({ forcePushes: undefined })],
    ['date de push forcé illisible', broken({ forcePushes: ['demain'] })],
    ['runs absents', broken({ runs: undefined })],
    ['run sans branche', broken({ runs: [{ ...EXPECTED.runs[0], headBranch: undefined }] })],
    ['pull absent', broken({ pull: undefined })],
    ['labels de la PR absents', broken({ pull: { ...EXPECTED.pull, labels: 'x' } })],
  ])('rend undefined pour : %s', (_name, value) => {
    expect(parseApprovalEvidence(value)).toBeUndefined();
  });
});
