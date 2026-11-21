import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadProtectedPaths } from '../protected-paths.ts';
import { evaluateCommand } from './bash-guard.ts';

const ROOT = resolve(import.meta.dirname, '..', '..');
const SCRIPT = resolve(import.meta.dirname, 'bash-guard.ts');
const GLOBS = (await loadProtectedPaths(ROOT)).paths;

const WRITES = [
  "sed -i 's/a/b/' eslint.config.mjs",
  'echo x > quality/baseline.json',
  'tee -a .github/workflows/quality.yml',
  'mv x quality/run.ts',
  'cp x package.json',
  'rm -rf quality',
  'git checkout -- lefthook.yml',
  'git restore tsconfig.json',
  'echo x >> mise.toml',
  'cat x | tee quality/x.ts',
  'sed -i.bak s/a/b/ stryker.config.mjs',
  'sed -ni s/a/b/p biome.json',
  'rm -rf .claude',
  'rm -rf .',
  'rm -rf *',
  'mv .github elsewhere',
  'cp x ./quality/y.ts',
  'echo x > src/../quality/y.ts',
  'echo x &> .npmrc',
  'ln -s x package.json',
  'truncate -s 0 pnpm-lock.yaml',
  'dd if=x of=eslint.config.mjs',
  'git rm quality/run.ts',
  'git checkout HEAD -- .semgrepignore',
  'mise exec -- sed -i s/a/b/ biome.json',
  'FOO=1 sed -i s/a/b/ biome.json',
  'env sed -i s/a/b/ biome.json',
  'echo $(sed -i s/a/b/ biome.json)',
  'echo ok && sed -i s/a/b/ biome.json',
  'perl -pi -e s/a/b/ .npmrc',
  'rm .git/hooks/pre-commit',
  "sh -c 'sed -i s/a/b/ quality/x.ts'",
  'bash -c "gh pr merge 3 --squash"',
  'sh -c "sh -c \'echo x > quality/y.ts\'"',
  'eval "echo x > quality/y.ts"',
];

const HOOKS = [
  'git commit --no-verify -m x',
  'git commit -n -m x',
  'git commit -anm x',
  'git push --force',
  'git push -f origin x',
  'git push --force-with-lease origin x',
  'git push origin +x',
  'LEFTHOOK=0 git commit -m x',
  'export LEFTHOOK="0"',
  'git -c core.hooksPath=/dev/null commit',
  'git config core.hooksPath x',
  'lefthook uninstall',
  'PROSPERITY_HUMAN_GATE_EDIT=1 git commit -m x',
  'echo PROSPERITY_HUMAN_GATE_EDIT',
  'echo disableAllHooks',
  'git -C . push --force',
];

const SIGNATURE = [
  'git commit --allow-empty -S -m x',
  'git commit -aS -m x',
  'git commit --gpg-sign -m x',
  'git commit --gpg-sign=ABC -m x',
  'git commit -m "gate-approval: gate-change-approved"',
  'git commit -m "Gate-Approval: deps-approved"',
  'git -c user.signingkey=/tmp/k commit -m x',
  'git -c gpg.format=ssh commit -m x',
  'git config --global commit.gpgsign true',
  'git tag -s v1',
  'git rebase -S main',
  'ssh-keygen -Y sign -f /tmp/k -n git f',
  'ssh-keygen -t ed25519-sk',
  'ssh-add /tmp/k',
  'gh ssh-key add k.pub --type signing',
  'gh gpg-key add k.asc',
  'gh api user/ssh_signing_keys',
];

const GITHUB = [
  'gh pr edit 3 --add-label gate-change-approved',
  'gh issue edit 3 --remove-label x',
  'gh pr create --label x',
  'gh label create x',
  'gh api -X POST repos/o/r/issues/3/labels',
  'gh api --method PUT repos/o/r/rulesets/1',
  'gh api -XDELETE repos/o/r/issues/3/labels/x',
  'gh api repos/o/r/issues/3/labels -f labels=x',
  'gh api repos/o/r/issues/3/labels --input body.json',
  "gh api graphql -f query='mutation { addLabelsToLabelable(input: {}) { clientMutationId } }'",
  'gh auth token',
  'gh auth status --show-token',
  'curl -X POST https://api.github.com/x',
  'wget https://api.github.com/user',
  'pnpm add x',
  'pnpm remove x',
  'mise exec -- pnpm add x',
  'pnpm install left-pad',
  'gh pr merge 3 --squash',
  'gh pr merge 3 --auto',
  'gh pr review 3 --approve',
  'gh repo edit --enable-auto-merge',
  'gh secret set GATE_APP_PRIVATE_KEY',
  'gh variable set GATE_APP_ID',
  'gh workflow disable quality-verdict',
  'git push origin HEAD:main',
  'git push origin main',
  'git push -u origin refs/heads/main',
  'git push origin feature:main',
];

const ALLOWED = [
  'git status',
  'mise exec -- pnpm quality --profile push',
  'gh pr view 3 --json labels',
  'gh pr create --draft --base main --head x',
  'gh pr checks 3',
  'gh ruleset view 17645569',
  'sed -n 1,10p eslint.config.mjs',
  'cat quality/baseline.json',
  'echo x > src/a.ts',
  'git commit -m "feat: x"',
  'git push origin sebc-dev/x',
  'git commit -mfinal',
  'git commit -am "feat: y"',
  'git log -S needle --oneline',
  'git diff --cached --stat',
  'git checkout -b feature/x',
  'git checkout main',
  'git restore --staged src/a.ts',
  'git push -u origin sebc-dev/y',
  'gh pr list --label bug',
  'gh pr create --title x --body "ne jamais git push --force ni --no-verify"',
  'gh api repos/o/r/pulls/3 --jq .title',
  'gh api repos/o/r/issues/3/labels',
  'gh auth status',
  'pnpm install --frozen-lockfile',
  'rm -rf node_modules reports/x',
  'mv src/a.ts src/b.ts',
  'cp quality/run.ts /tmp/copy.ts',
  'echo x > reports/out.json 2>&1',
  'echo x > /dev/null',
  'ls -la src | head',
  'sed -n -e s/a/b/p package.json',
];

function expectDeny(command: string): void {
  expect(evaluateCommand(command, GLOBS)).toMatchObject({
    decision: 'deny',
    reason: expect.stringMatching(/\S/),
  });
}

describe('evaluateCommand : refus', () => {
  it.each(WRITES)('refuse l’écriture shell vers un chemin protégé : %s', expectDeny);
  it.each(HOOKS)('refuse le contournement des hooks : %s', expectDeny);
  it.each(SIGNATURE)('refuse la signature et les clés (D-14) : %s', expectDeny);
  it.each(GITHUB)('refuse les gestes réservés à l’humain : %s', expectDeny);
});

describe('evaluateCommand : autorisations', () => {
  it.each(ALLOWED)('laisse passer : %s', (command) => {
    expect(evaluateCommand(command, GLOBS)).toEqual({ decision: 'allow' });
  });

  it('relativise un chemin absolu sous le répertoire de travail', () => {
    expect(evaluateCommand(`echo x > ${ROOT}/quality/y.ts`, GLOBS, ROOT).decision).toBe('deny');
    expect(evaluateCommand(`echo x > ${ROOT}/src/y.ts`, GLOBS, ROOT).decision).toBe('allow');
  });

  it('ne retient aucune règle d’écriture quand la liste des chemins protégés est vide', () => {
    expect(evaluateCommand('sed -i s/a/b/ eslint.config.mjs', []).decision).toBe('allow');
    expect(evaluateCommand('git commit --no-verify -m x', []).decision).toBe('deny');
  });

  it('refuse une commande imbriquée au-delà de la profondeur analysable', () => {
    const nested = Array.from({ length: 7 }).reduce<string>(
      (command) => `sh -c ${JSON.stringify(command)}`,
      'echo x',
    );
    expect(evaluateCommand(nested, GLOBS).decision).toBe('deny');
    expect(evaluateCommand('sh -c "sh -c \'echo x\'"', GLOBS).decision).toBe('allow');
  });
});

function hook(input: string): { code: number | null; out: string } {
  const run = spawnSync(process.execPath, [SCRIPT], { input, encoding: 'utf8', cwd: ROOT });
  return { code: run.status, out: run.stdout };
}

function payload(command: string): string {
  return JSON.stringify({ tool_name: 'Bash', tool_input: { command } });
}

describe('bash-guard.ts : processus réel', () => {
  it('écrit le refus PreToolUse sur stdout avec le code 0', () => {
    const { code, out } = hook(payload('sed -i s/a/b/ eslint.config.mjs'));
    expect(code).toBe(0);
    expect(JSON.parse(out)).toEqual({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: expect.stringContaining('eslint.config.mjs'),
      },
    });
  });

  it('refuse une fusion de PR, directe ou imbriquée dans bash -c', () => {
    expect(hook(payload('gh pr merge 3 --squash')).out).toContain('"permissionDecision":"deny"');
    expect(hook(payload('bash -c "gh pr merge 3 --auto"')).out).toContain(
      '"permissionDecision":"deny"',
    );
  });

  it('ne dit rien pour une commande autorisée', () => {
    expect(hook(payload('ls -la src'))).toEqual({ code: 0, out: '' });
  });

  it.each(['pas du JSON', '{}', '{"tool_input":{}}', '{"tool_input":{"command":3}}', ''])(
    'ne décide rien pour une entrée illisible : %j',
    (input) => {
      expect(hook(input)).toEqual({ code: 0, out: '' });
    },
  );
});
