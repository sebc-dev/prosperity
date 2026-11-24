import { basename, resolve } from 'node:path';
import { loadProtectedPaths } from '../protected-paths.ts';
import { isRecord } from '../tools.ts';
import { ghDenial } from './gh-rules.ts';
import { gitDenial } from './git-rules.ts';
import { downloadDenial, lefthookDenial, packageDenial, sshDenial } from './misc-rules.ts';
import { splitCommand } from './shell-split.ts';
import type { Segment } from './shell-split.ts';
import { redirectDenial, writeCommandDenial } from './write-rules.ts';
import type { Denial } from './write-rules.ts';

// Hook PreToolUse (Bash) de l'agent : refuse les écritures shell vers la gate et les
// gestes réservés à l'humain. Inactif jusqu'au plan 01-14 (D-01). Pas exhaustif par
// décision (D-04) : la CI est le juge final.

export type Decision = { decision: 'allow' } | { decision: 'deny'; reason: string };

const MAX_DEPTH = 4;
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash', 'ksh']);
const WRAPPERS = new Set([
  'env',
  'command',
  'exec',
  'time',
  'nohup',
  'sudo',
  'builtin',
  'nice',
  'setsid',
  'stdbuf',
  '!',
  '{',
  'then',
  'do',
  'else',
]);
const PACKAGE_MANAGERS = new Set(['pnpm', 'npm', 'yarn']);
const ASSIGNMENT = /^[A-Za-z_]\w*=/;
const SHORT_FLAGS = /^-[A-Za-z]+$/;
const RAW_DENIALS: readonly (readonly [RegExp, string])[] = [
  [
    /PROSPERITY_HUMAN_GATE_EDIT/,
    "la variable d'autorisation humaine ne se pose pas depuis l'agent",
  ],
  [/disableAllHooks/, 'disableAllHooks désarme les hooks'],
  [/\bLEFTHOOK\s*=\s*["']?0\b/, 'LEFTHOOK=0 contourne les hooks'],
];

/** Retire affectations d'environnement et enveloppes (`env`, `sudo`, `mise exec --`, `pnpm exec`). */
function unwrap(words: readonly string[]): string[] {
  let rest = [...words];
  let wrapped = false;
  for (let guard = 0; guard < words.length && rest.length > 0; guard += 1) {
    const head = rest[0] ?? '';
    const name = basename(head);
    const isWrapper = ASSIGNMENT.test(head) || WRAPPERS.has(name);
    if (isWrapper || (wrapped && head.startsWith('-'))) {
      rest = rest.slice(1);
    } else if (name === 'mise' && rest.includes('--')) {
      rest = rest.slice(rest.indexOf('--') + 1);
    } else if ((PACKAGE_MANAGERS.has(name) && rest[1] === 'exec') || name === 'timeout') {
      rest = rest.slice(2);
    } else {
      break;
    }
    wrapped = isWrapper;
  }
  return rest;
}

/** Script passé à un shell (`sh -c '…'`) ou à `eval` : il est analysé à son tour. */
function nestedScript(name: string, words: readonly string[]): string | undefined {
  if (name === 'eval') {
    return words.slice(1).join(' ');
  }
  if (!SHELLS.has(name)) {
    return undefined;
  }
  const flag = words.findIndex(
    (word, index) => index > 0 && SHORT_FLAGS.test(word) && word.includes('c'),
  );
  return flag === -1 ? undefined : words[flag + 1];
}

type Rule = (words: readonly string[], globs: readonly string[], cwd: string | undefined) => Denial;

const RULES = new Map<string, Rule>([
  ['git', gitDenial],
  ['gh', (words) => ghDenial(words)],
  ['lefthook', (words) => lefthookDenial(words.slice(1))],
  ['curl', (words) => downloadDenial(words.slice(1))],
  ['wget', (words) => downloadDenial(words.slice(1))],
  ['ssh-keygen', () => sshDenial('ssh-keygen')],
  ['ssh-add', () => sshDenial('ssh-add')],
  ...[...PACKAGE_MANAGERS].map((manager): [string, Rule] => [
    manager,
    (words) => packageDenial(manager, words.slice(1)),
  ]),
]);

function commandDenial(
  name: string,
  words: readonly string[],
  globs: readonly string[],
  cwd: string | undefined,
): Denial {
  return (
    RULES.get(name)?.(words, globs, cwd) ?? writeCommandDenial(name, words.slice(1), globs, cwd)
  );
}

function segmentDenial(
  segment: Segment,
  globs: readonly string[],
  cwd: string | undefined,
  depth: number,
): Denial {
  const redirected = redirectDenial(segment.writes, globs, cwd);
  if (redirected !== undefined) {
    return redirected;
  }
  const words = unwrap(segment.words);
  const name = basename(words[0] ?? '');
  const script = nestedScript(name, words);
  if (script !== undefined) {
    return inspect(script, globs, cwd, depth + 1);
  }
  return name === '' ? undefined : commandDenial(name, words, globs, cwd);
}

function inspect(
  command: string,
  globs: readonly string[],
  cwd: string | undefined,
  depth: number,
): Denial {
  if (depth > MAX_DEPTH) {
    return 'commande imbriquée trop profondément pour être analysée';
  }
  const raw = RAW_DENIALS.find(([pattern]) => pattern.test(command));
  if (raw !== undefined) {
    return raw[1];
  }
  for (const segment of splitCommand(command)) {
    const reason = segmentDenial(segment, globs, cwd, depth);
    if (reason !== undefined) {
      return reason;
    }
  }
  return undefined;
}

/** Décision pour une commande Bash : `deny` avec la raison, ou `allow`. `cwd` relativise les chemins absolus. */
export function evaluateCommand(
  command: string,
  protectedGlobs: readonly string[],
  cwd?: string,
): Decision {
  const reason = inspect(command, protectedGlobs, cwd, 0);
  return reason === undefined ? { decision: 'allow' } : { decision: 'deny', reason };
}

async function readStdin(): Promise<string> {
  process.stdin.setEncoding('utf8');
  let text = '';
  for await (const chunk of process.stdin) {
    text += String(chunk);
  }
  return text;
}

async function loadGlobs(): Promise<string[]> {
  try {
    const { paths, agentExempt } = await loadProtectedPaths(
      resolve(import.meta.dirname, '..', '..'),
    );
    return paths.filter((glob) => !agentExempt.includes(glob));
  } catch {
    // Liste illisible : seuls les refus inconditionnels s'appliquent.
    return [];
  }
}

async function main(): Promise<void> {
  try {
    const input: unknown = JSON.parse(await readStdin());
    const toolInput = isRecord(input) ? input['tool_input'] : undefined;
    const command = isRecord(toolInput) ? toolInput['command'] : undefined;
    if (typeof command !== 'string') {
      return;
    }
    const verdict = evaluateCommand(command, await loadGlobs(), process.cwd());
    if (verdict.decision === 'deny') {
      process.stdout.write(
        JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'deny',
            permissionDecisionReason: verdict.reason,
          },
        }),
      );
    }
  } catch {
    // Entrée illisible : aucune décision (code 0, aucune sortie). La CI reste le juge (D-04).
  }
}

if (import.meta.main) {
  await main();
}
