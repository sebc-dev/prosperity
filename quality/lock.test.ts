import { spawnSync } from 'node:child_process';
import { mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadProtectedPaths } from './protected-paths.ts';
import { clearRepoGitVariables, isRecord, runTool } from './tools.ts';

// Test du verrou (plan 01-14, D-01) : cohérence des règles de l'agent, des workflows et de la
// liste unique des chemins protégés, puis refus de bout en bout.

const ROOT = resolve(import.meta.dirname, '..');
const read = (path: string): Promise<string> => readFile(join(ROOT, path), 'utf8');
const { paths: PATHS, agentExempt: EXEMPT } = await loadProtectedPaths(ROOT);
const PINNED_USES = /^(- )?uses: \S+@[0-9a-f]{40}( #.*)?$/;

function strings(value: unknown): string[] {
  const items: unknown[] = Array.isArray(value) ? value : [];
  return items.filter((item) => typeof item === 'string');
}

async function loadSettings() {
  const parsed: unknown = JSON.parse(await read('.claude/settings.json'));
  const permissions = isRecord(parsed) ? parsed['permissions'] : undefined;
  const rules = isRecord(permissions) ? permissions : {};
  return {
    deny: strings(rules['deny']),
    others: [...strings(rules['ask']), ...strings(rules['allow'])],
    raw: JSON.stringify(parsed),
  };
}

/** Règle `Edit(...)` d'un motif : `/` initial à la racine, `**` + `/` gardé pour toute profondeur. */
const editRule = (glob: string): string =>
  glob.startsWith('**/') ? `Edit(${glob})` : `Edit(/${glob})`;

/** Bloc d'un job (indentation 2) d'un workflow lu en texte. */
function jobBlock(text: string, job: string): string {
  const lines = text.split('\n');
  const start = lines.findIndex((line) => line === `  ${job}:`);
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((line) => /^ {2}\S/.test(line));
  return (end === -1 ? rest : rest.slice(0, end)).join('\n');
}

const stepsOf = (block: string): string[] => block.split(/^ {6}- /m).slice(1);
const stepNamed = (block: string, name: string): string =>
  stepsOf(block).find((step) => step.startsWith(`name: ${name}\n`)) ?? '';

function jobNames(text: string): string[] {
  const after = text.split(/^jobs:$/m)[1] ?? '';
  return [...after.matchAll(/^ {2}([\w-]+):\s*$/gm)].map((match) => match[1] ?? '');
}

describe('.claude/settings.json : règles de l’agent', () => {
  it('refuse l’édition de chaque chemin protégé par une règle Edit (Edit, Write et NotebookEdit)', async () => {
    const { deny } = await loadSettings();
    const missing = PATHS.filter((glob) => !EXEMPT.includes(glob)).filter(
      (glob) => !deny.includes(editRule(glob)),
    );
    expect(missing).toEqual([]);
  });

  it('n’écrit aucune règle Write à chemin, acceptée par Claude Code sans jamais être appliquée', async () => {
    // [CITED: code.claude.com/docs/en/permissions] « Edit rules apply to all built-in tools that
    // edit files » : Edit, Write et NotebookEdit. Une règle Write portant un chemin ne matche pas.
    const { deny, others } = await loadSettings();
    expect([...deny, ...others].filter((rule) => rule.startsWith('Write('))).toEqual([]);
  });

  it('déclare le hook PreToolUse Bash vers le garde', async () => {
    const { raw } = await loadSettings();
    expect(raw).toContain('"matcher":"Bash"');
    expect(raw).toContain('quality/agent-guard/bash-guard.ts');
  });

  it.each([
    ['labels', ['gh pr edit*', 'gh issue edit*', 'gh label*', 'gh api*labels*']],
    ['fusion et revue', ['gh pr merge*', 'gh pr review*']],
    ['réglages', ['gh repo edit*', 'gh secret*', 'gh variable*', 'gh api*environments*']],
    ['API en écriture', ['gh api*-X*', 'gh api*--method*', 'gh api* -f *', 'gh api*--input*']],
    ['hooks et push', ['git commit*--no-verify*', 'git push*--force*', 'git push* main']],
    ['signature et clés', ['git commit* -S*', 'ssh-keygen*', 'ssh-add*', 'gh ssh-key*']],
  ])('refuse les gestes réservés à l’humain : %s', async (_family, commands) => {
    const { deny } = await loadSettings();
    expect(commands.filter((command) => !deny.includes(`Bash(${command})`))).toEqual([]);
  });
});

describe('CODEOWNERS et pré-commit', () => {
  it('donne une ligne CODEOWNERS à chaque chemin protégé', async () => {
    const lines = (await read('.github/CODEOWNERS')).split('\n');
    expect(PATHS.filter((glob) => !lines.includes(`${glob} @sebc-dev`))).toEqual([]);
  });

  it('branche le refus des chemins protégés au pré-commit et la gate au pré-push', async () => {
    const lefthook = await read('lefthook.yml');
    expect(lefthook).toContain('name: protected-paths');
    expect(lefthook).toContain('quality/agent-guard/precommit-protected.ts');
    expect(lefthook).toMatch(/^pre-push:/m);
    expect(lefthook).toContain('name: quality-push');
  });
});

describe('workflow quality', () => {
  it('garde le nom `quality`, deux jobs `gate` et `reset-approval`, aucun job `quality`', async () => {
    const text = await read('.github/workflows/quality.yml');
    expect(text).toMatch(/^name: quality$/m);
    expect(jobNames(text)).toEqual(['gate', 'reset-approval']);
    expect(text).not.toMatch(/^ {4}name: quality\s*$/m);
  });

  it('déclenche sans filtre de chemins ni `_target`, sur les cinq types d’activité', async () => {
    const text = await read('.github/workflows/quality.yml');
    expect(text).not.toMatch(/\bpaths(-ignore)?:/);
    expect(text).not.toContain('_target');
    expect(text).toContain('types: [opened, synchronize, reopened, labeled, unlabeled]');
  });

  it('ne conditionne pas `gate` et ne donne d’écriture qu’à `reset-approval`', async () => {
    const text = await read('.github/workflows/quality.yml');
    expect(jobBlock(text, 'gate')).not.toMatch(/^ {4}if:/m);
    const writes = text.split('\n').filter((line) => line.includes(': write'));
    expect(writes.map((line) => line.trim().split(' ')[0])).toEqual(['pull-requests:']);
    expect(jobBlock(text, 'reset-approval')).toContain('pull-requests: write');
    expect(jobBlock(text, 'reset-approval')).toContain('continue-on-error: true');
    expect(jobBlock(text, 'reset-approval')).not.toContain('uses:');
  });

  it('collecte les preuves avec le seul jeton du workflow, puis juge sans jeton depuis la base', async () => {
    const gate = jobBlock(await read('.github/workflows/quality.yml'), 'gate');
    expect(stepNamed(gate, 'approval-evidence')).toContain('GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}');
    for (const name of ['approvals', 'integrity', 'deps']) {
      const step = stepNamed(gate, name);
      const commands = step.split('\n').filter((line) => line.trim().startsWith('node '));
      expect(step).not.toContain('GH_TOKEN');
      expect(commands).toHaveLength(2);
      expect(
        commands.filter((line) => !line.includes('--base-dir "$RUNNER_TEMP/gate-base"')),
      ).toEqual([]);
    }
    expect(gate).toContain('gate-base/quality/integrity.ts');
  });

  it('installe les outils hors npm depuis mise.lock et épingle chaque action par SHA', async () => {
    const dir = join(ROOT, '.github', 'workflows');
    for (const file of await readdir(dir)) {
      const lines = (await readFile(join(dir, file), 'utf8')).split('\n');
      expect(
        lines.filter((line) => /\buses:/.test(line) && !PINNED_USES.test(line.trim())),
      ).toEqual([]);
    }
    for (const file of ['quality.yml', 'nightly.yml']) {
      expect(await read(`.github/workflows/${file}`)).toContain('install_args: "--locked"');
    }
  });
});

describe('workflow quality-verdict', () => {
  it('se déclenche par workflow_run, sous l’environnement du juge, en lecture seule', async () => {
    const text = await read('.github/workflows/quality-verdict.yml');
    expect(text).toMatch(/^ {2}workflow_run:\n {4}workflows: \[quality\]/m);
    expect(text).toContain('environment: gate-verdict');
    // `permission-statuses: write` est une entrée de l'action qui crée le jeton de l'application,
    // pas une permission du jeton du workflow.
    const writes = text.split('\n').filter((line) => /^\s+(?!permission-)[\w-]+: write/.test(line));
    expect(writes).toEqual([]);
  });

  it('n’installe aucune dépendance et ne lit que la branche par défaut', async () => {
    const text = await read('.github/workflows/quality-verdict.yml');
    expect(
      text.split('\n').filter((line) => /(pnpm|npm|yarn) (install|ci|add)/.test(line)),
    ).toEqual([]);
    expect(text.split('\n').filter((line) => line.trim().startsWith('ref:'))).toEqual([]);
  });
});

function guardDecision(command: string): string {
  const input = JSON.stringify({ tool_name: 'Bash', tool_input: { command } });
  const script = join(ROOT, 'quality', 'agent-guard', 'bash-guard.ts');
  return spawnSync(process.execPath, [script], { input, encoding: 'utf8', cwd: ROOT }).stdout;
}

describe('garde Bash : refus de bout en bout (D-01, D-15)', () => {
  it.each([
    "sed -i 's/80/70/' eslint.config.mjs",
    'gh pr merge 3 --squash',
    'gh pr edit 3 --add-label gate-change-approved',
    'gh api -X POST repos/sebc-dev/prosperity/issues/3/labels -f labels[]=deps-approved',
  ])('refuse : %s', (command) => {
    expect(guardDecision(command)).toContain('"permissionDecision":"deny"');
  });
});

const TRIVIAL_WORKFLOW =
  'name: quality\non: pull_request\njobs:\n  gate:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: "true"\n';
const GATE_PATH = '.github/workflows/quality.yml';

async function git(args: readonly string[]): Promise<void> {
  const env = { ...process.env };
  clearRepoGitVariables(env);
  const run = await runTool({ command: 'git', args: ['-C', ROOT, ...args], cwd: ROOT, env });
  expect({ args, code: run.code, stderr: run.stderr }).toMatchObject({ code: 0 });
}

async function verdictOf(
  scratch: string,
  approved: string[],
): Promise<{ stdout: string; verdict: string }> {
  const report = { approved, rejected: [], bootstrap: false, verifier: 'github-label-events@1' };
  const approval =
    approved.length === 0
      ? null
      : { commit: 'a'.repeat(40), principal: 'sebc-dev', keyType: 'github-label', flags: null };
  const reportPath = join(scratch, 'approvals-in.json');
  await writeFile(reportPath, JSON.stringify({ ...report, approval }));
  const out = join(scratch, 'verdict.json');
  const run = await runTool({
    command: process.execPath,
    args: [
      join(ROOT, 'quality', 'verdict.ts'),
      ...['--dry-run', '--base-dir', join(scratch, 'base'), '--head-dir', join(scratch, 'head')],
      ...['--work-dir', join(scratch, 'work'), '--out', out, '--approvals-report', reportPath],
      ...['--gate-conclusion', 'success', '--gate-path', GATE_PATH, '--gate-event', 'pull_request'],
    ],
    cwd: scratch,
    env: { PATH: process.env['PATH'] ?? '' },
    timeoutMs: 120_000,
  });
  expect({ code: run.code, stderr: run.stderr }).toEqual({ code: 0, stderr: '' });
  return { stdout: run.stdout, verdict: await readFile(out, 'utf8') };
}

describe('juge hors PR en --dry-run : une PR qui réécrit quality.yml (D-15)', () => {
  it('rend failure sans le label, success avec `gate-change-approved`', async () => {
    const scratch = await mkdtemp(join(tmpdir(), 'lock-verdict-'));
    try {
      await git(['worktree', 'add', '--detach', join(scratch, 'base'), 'HEAD']);
      await git(['worktree', 'add', '--detach', join(scratch, 'head'), 'HEAD']);
      await writeFile(join(scratch, 'head', GATE_PATH), TRIVIAL_WORKFLOW);
      const refused = await verdictOf(scratch, []);
      expect(JSON.parse(refused.stdout)).toMatchObject({ state: 'failure', context: 'quality' });
      expect(refused.verdict).toContain('protected-path-changed');
      const accepted = await verdictOf(scratch, ['gate-change-approved']);
      expect(JSON.parse(accepted.stdout)).toMatchObject({ state: 'success' });
    } finally {
      await git(['worktree', 'remove', '--force', join(scratch, 'base')]).catch(() => undefined);
      await git(['worktree', 'remove', '--force', join(scratch, 'head')]).catch(() => undefined);
      await rm(scratch, { recursive: true, force: true });
    }
  }, 240_000);
});
