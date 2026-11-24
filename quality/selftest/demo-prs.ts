import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { isRecord, runMiseTool, runTool } from '../tools.ts';
import { loadCases } from './cases.ts';

/**
 * Outil EXÉCUTÉ PAR L'HUMAIN pour le passage manuel D-07b : il ouvre des PR de démonstration et
 * imprime les gestes humains qui suivent. Il ne crée, ne pose ni ne retire jamais de label avec le
 * jeton de l'humain (seul le workflow temporaire de `bot-label` en pose un, sous
 * `github-actions[bot]`), et il ne pose jamais `PROSPERITY_HUMAN_GATE_EDIT` lui-même.
 */

const ROOT = resolve(import.meta.dirname, '..', '..');
const EXIT_OK = 0;
const EXIT_FAILURE = 1;
const EXIT_USAGE = 2;
const COMMAND_TIMEOUT_MS = 600_000;
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const RERUN_POLLS = 12;
const RERUN_POLL_MS = 5_000;
// Les hooks locaux sont coupés pour les commits et pushes de démonstration : la violation voulue
// doit atteindre GitHub, où la CI est le seul juge.
const NO_HOOKS: NodeJS.ProcessEnv = { LEFTHOOK: '0' };
const ACTIVE_PACKAGES = ['typescript', 'vitest', 'eslint', 'knip', 'kysely', 'pg'];
const MATURITY_ERROR = /minimumReleaseAge|NO_MATURE_MATCHING_VERSION/i;
const SEMVER_RELEASE = /^\d+\.\d+\.\d+$/;

const SCENARIOS = [
  'blocked-check',
  'human-label',
  'bot-label',
  'deps-unapproved',
  'workflow-rewrite',
  'deps-too-recent',
] as const;
type Scenario = (typeof SCENARIOS)[number];
type PrScenario = Exclude<Scenario, 'deps-too-recent'>;
type ApplyFunction = (root: string) => Promise<void>;

const USAGE = `Usage : PROSPERITY_HUMAN_GATE_EDIT=1 node quality/selftest/demo-prs.ts <scénario>

Scénarios : ${SCENARIOS.join(', ')}

L'outil ouvre une PR de démonstration (branche demo/gate-<scénario> depuis origin/main) puis
imprime les gestes humains. Il refuse de tourner sans PROSPERITY_HUMAN_GATE_EDIT=1 dans
l'environnement de l'appelant, qu'il ne pose jamais lui-même.`;

const QUALITY_REWRITE = `name: quality
on:
  pull_request:
jobs:
  gate:
    runs-on: ubuntu-24.04
    permissions: {}
    steps:
      - run: "true"
`;

const BOT_LABEL_WORKFLOW = `name: demo-bot-label
on:
  pull_request:
    types: [opened]
permissions: {}
jobs:
  label:
    runs-on: ubuntu-24.04
    permissions:
      pull-requests: write
    steps:
      - run: gh pr edit "$PR" --repo "$REPO" --add-label gate-change-approved
        env:
          GH_TOKEN: \${{ secrets.GITHUB_TOKEN }}
          PR: \${{ github.event.pull_request.number }}
          REPO: \${{ github.repository }}
`;

function say(line = ''): void {
  process.stdout.write(`${line}\n`);
}

function isScenario(value: string): value is Scenario {
  return SCENARIOS.some((scenario) => scenario === value);
}

function isApplyFunction(value: unknown): value is ApplyFunction {
  return typeof value === 'function';
}

async function run(
  command: string,
  args: readonly string[],
  cwd: string,
  extraEnv: NodeJS.ProcessEnv = {},
): Promise<string> {
  const env = { ...process.env, ...extraEnv };
  const result = await runTool({ command, args, cwd, env, timeoutMs: COMMAND_TIMEOUT_MS });
  if (result.code !== 0) {
    const tail = result.stderr.trim().slice(-400);
    throw new Error(
      `${command} ${args.join(' ')} a échoué (code ${String(result.code)}) : ${tail}`,
    );
  }
  return result.stdout.trim();
}

/** Applique un cas d'auto-test dans `target` : un `patch` git ou la fonction exportée par `apply.ts`. */
async function applyCase(id: string, target: string): Promise<void> {
  const found = (await loadCases(ROOT)).find((item) => item.id === id);
  if (found === undefined) {
    throw new Error(`cas d'auto-test introuvable : ${id}`);
  }
  if (found.kind === 'patch') {
    await run('git', ['apply', '--index', join(found.dir, 'patch')], target);
    return;
  }
  const loaded: unknown = await import(pathToFileURL(join(found.dir, 'apply.ts')).href);
  const apply = isRecord(loaded) ? loaded['default'] : undefined;
  if (!isApplyFunction(apply)) {
    throw new Error(`${id} : apply.ts doit exporter par défaut une fonction apply(root)`);
  }
  await apply(target);
}

async function addUnapprovedDependency(target: string): Promise<void> {
  const args = ['exec', '--', 'pnpm', 'add', '--save-exact', '--lockfile-only', 'ms@2.1.3'];
  await run('mise', args, target);
}

async function writeWorkflow(target: string, name: string, content: string): Promise<void> {
  const directory = join(target, '.github', 'workflows');
  await mkdir(directory, { recursive: true });
  await writeFile(join(directory, name), content, 'utf8');
}

const MUTATIONS: Record<PrScenario, (target: string) => Promise<void>> = {
  'blocked-check': (target) => applyCase('lint-type-assertion', target),
  'human-label': (target) => applyCase('integrity-protected-path-changed', target),
  'bot-label': async (target) => {
    await applyCase('integrity-protected-path-changed', target);
    await writeWorkflow(target, 'demo-bot-label.yml', BOT_LABEL_WORKFLOW);
  },
  'deps-unapproved': addUnapprovedDependency,
  'workflow-rewrite': (target) => writeWorkflow(target, 'quality.yml', QUALITY_REWRITE),
};

const VERDICT_HINT =
  "Lire la raison dans l'artefact `verdict` du run `quality-verdict` (gh run download <id> -n verdict).";

const GESTURES: Record<PrScenario, (pr: string) => string[]> = {
  'blocked-check': () => [
    'Attendu : le check `lint` échoue pour la règle @typescript-eslint/consistent-type-assertions,',
    'le statut requis `quality` est rouge et la fusion est bloquée.',
    VERDICT_HINT,
  ],
  'human-label': (pr) => [
    '1. Relire le diff de la PR (la PR modifie un chemin protégé : `integrity` exige `gate-change-approved`).',
    "2. Constater `quality` rouge (`protected-path-changed`) tant qu'aucun label n'est posé.",
    `3. Poser le label APRÈS le dernier push : gh pr edit ${pr} --add-label gate-change-approved`,
    '4. Attendre le rejeu du workflow `quality` (événement labeled) : `quality` doit passer au vert.',
    `5. Pousser un commit vide ordinaire : gh pr checkout ${pr} && git commit --allow-empty -m "demo: push suivant" && git push`,
    '6. Constater que `reset-approval` retire le label et que `quality` redevient rouge (`approval-removed` ou `approval-stale`).',
    VERDICT_HINT,
  ],
  'bot-label': () => [
    'Le workflow temporaire `demo-bot-label` pose `gate-change-approved` sous `github-actions[bot]`.',
    "Un label posé par le jeton d'un workflow ne relance aucun run : relancer le run `quality` de la PR",
    '(commande imprimée ci-dessous) une fois le run `demo-bot-label` terminé.',
    'Attendu : `quality` reste rouge, raison `approval-actor-not-allowed`.',
    VERDICT_HINT,
  ],
  'deps-unapproved': () => [
    'Attendu : le check `deps` échoue (dépendance ajoutée sans `deps-approved`), `quality` est rouge.',
    'Ne PAS poser `deps-approved` pour ce scénario (preuve du refus).',
    VERDICT_HINT,
  ],
  'workflow-rewrite': () => [
    "Attendu : le job `gate` de la PR est vert (le workflow réécrit n'exécute que `true`) mais le statut",
    "requis `quality`, publié par le juge hors PR, est rouge avec `protected-path-changed` tant qu'aucun",
    "label approuvé n'est posé : une PR ne peut pas se juger elle-même en réécrivant son workflow.",
    VERDICT_HINT,
  ],
};

async function pause(ms: number): Promise<void> {
  await new Promise<void>((done) => {
    setTimeout(done, ms);
  });
}

/** Cherche le run `quality` de la branche ; imprime la commande de relance que l'humain lance. */
async function printRerun(branch: string): Promise<void> {
  const args = ['run', 'list', '--branch', branch, '--workflow', 'quality', '--limit', '1'];
  for (let attempt = 0; attempt < RERUN_POLLS; attempt += 1) {
    const id = await run('gh', [...args, '--json', 'databaseId', '--jq', '.[0].databaseId'], ROOT);
    if (id !== '') {
      say(`Commande à lancer vous-même : gh run rerun ${id}`);
      return;
    }
    await pause(RERUN_POLL_MS);
  }
  say(`Run \`quality\` introuvable : gh run list --branch ${branch} --workflow quality`);
}

async function openPullRequest(scenario: PrScenario): Promise<void> {
  await run('git', ['fetch', 'origin', 'main'], ROOT);
  const branch = `demo/gate-${scenario}`;
  const dir = await mkdtemp(join(tmpdir(), 'demo-gate-'));
  const target = join(dir, 'checkout');
  await run('git', ['worktree', 'add', '-b', branch, target, 'origin/main'], ROOT);
  try {
    await MUTATIONS[scenario](target);
    await run('git', ['add', '--all'], target);
    await run('git', ['commit', '-q', '-m', `demo(gate): ${scenario}`], target, NO_HOOKS);
    await run('git', ['push', '-u', 'origin', branch], target, NO_HOOKS);
    const title = `demo(gate): ${scenario}`;
    const body = `PR de démonstration D-07b (${scenario}), à fermer sans fusionner.`;
    const create = ['pr', 'create', '--base', 'main', '--head', branch, '--title', title];
    const url = await run('gh', [...create, '--body', body], target);
    say(`PR ouverte : ${url}`);
    GESTURES[scenario](url.split('/').at(-1) ?? '<n>').forEach((line) => {
      say(line);
    });
    if (scenario === 'bot-label') {
      await printRerun(branch);
    }
  } finally {
    await run('git', ['worktree', 'remove', '--force', target], ROOT);
    await rm(dir, { recursive: true, force: true });
  }
}

/** Version stable publiée il y a moins de 7 jours, la plus récente ; `undefined` s'il n'y en a pas. */
async function recentVersion(name: string): Promise<string | undefined> {
  const times: unknown = JSON.parse(
    await run('mise', ['exec', '--', 'npm', 'view', name, 'time', '--json'], ROOT),
  );
  if (!isRecord(times)) {
    return undefined;
  }
  const limit = Date.now() - WEEK_MS;
  const fresh = Object.entries(times)
    .filter(([version]) => SEMVER_RELEASE.test(version))
    .flatMap(([version, stamp]) =>
      typeof stamp === 'string' ? [{ version, at: Date.parse(stamp) }] : [],
    )
    .filter(({ at }) => at > limit)
    .sort((a, b) => b.at - a.at);
  return fresh[0]?.version;
}

async function findRecentRelease(): Promise<{ name: string; version: string } | undefined> {
  for (const name of ACTIVE_PACKAGES) {
    const version = await recentVersion(name);
    if (version !== undefined) {
      return { name, version };
    }
  }
  return undefined;
}

/** Local seulement : `pnpm add` d'une version trop récente doit échouer sur `minimumReleaseAge`. */
async function tooRecentDemo(): Promise<number> {
  if ((await run('git', ['status', '--porcelain'], ROOT)) !== '') {
    throw new Error("arbre de travail non propre : committer ou ranger les changements d'abord");
  }
  const release = await findRecentRelease();
  if (release === undefined) {
    say(
      `Aucune version publiée depuis moins de 7 jours parmi ${ACTIVE_PACKAGES.join(', ')} : réessayer plus tard.`,
    );
    return EXIT_FAILURE;
  }
  const spec = `${release.name}@${release.version}`;
  say(`Version candidate : ${spec} (publiée il y a moins de 7 jours)`);
  const attempt = await runMiseTool('pnpm', ['add', '--save-exact', '--lockfile-only', spec], {
    cwd: ROOT,
    timeoutMs: COMMAND_TIMEOUT_MS,
  });
  const output = `${attempt.stdout}\n${attempt.stderr}`;
  if (attempt.code === 0) {
    await run('git', ['checkout', '--', 'package.json', 'pnpm-lock.yaml'], ROOT);
    say(`ÉCHEC : pnpm a accepté ${spec} malgré minimumReleaseAge (fichiers restaurés).`);
    return EXIT_FAILURE;
  }
  say(output.trim().slice(-600));
  say(
    MATURITY_ERROR.test(output) ? 'Erreur minimumReleaseAge attendue : OK.' : 'Erreur inattendue.',
  );
  return MATURITY_ERROR.test(output) ? EXIT_OK : EXIT_FAILURE;
}

async function main(argv: readonly string[]): Promise<number> {
  const name = argv[0] ?? '';
  if (process.env['PROSPERITY_HUMAN_GATE_EDIT'] !== '1' || !isScenario(name)) {
    say(USAGE);
    return EXIT_USAGE;
  }
  if (name === 'deps-too-recent') {
    return tooRecentDemo();
  }
  await openPullRequest(name);
  return EXIT_OK;
}

try {
  process.exitCode = await main(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : 'erreur inconnue'}\n`);
  process.exitCode = EXIT_FAILURE;
}
