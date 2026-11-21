import { hasShortFlag, nonOptions, touchesProtected } from './write-rules.ts';
import type { Denial } from './write-rules.ts';

interface GitCall {
  sub: string;
  args: string[];
  configs: string[];
}

// Configuration git qui désarme les hooks ou déclenche une signature (D-04, D-14).
const FORBIDDEN_CONFIG =
  /^(?:core\.hookspath|commit\.gpgsign|tag\.gpgsign|user\.signingkey|gpg\.)/i;
const APPROVAL_SUBJECT = /^(?:-m|--message=)?\s*gate-approval:/i;
const SIGNING_SUBS = new Set([
  'commit',
  'commit-tree',
  'merge',
  'rebase',
  'cherry-pick',
  'revert',
  'am',
  'pull',
]);
const PATH_WRITING_SUBS = new Set(['rm', 'mv']);
const DEFAULT_BRANCHES = new Set(['main', 'master']);

/** Options globales de `git` (`-c k=v`, `-C dir`…) avant le sous-commande. */
function parseGit(words: readonly string[]): GitCall {
  const configs: string[] = [];
  let index = 1;
  while (index < words.length) {
    const word = words[index] ?? '';
    if (word === '-c') {
      configs.push(words[index + 1] ?? '');
      index += 2;
    } else if (['-C', '--git-dir', '--work-tree', '--namespace'].includes(word)) {
      index += 2;
    } else if (word.startsWith('-')) {
      index += 1;
    } else {
      break;
    }
  }
  return { sub: words[index] ?? '', args: words.slice(index + 1), configs };
}

function signingDenial(call: GitCall): Denial {
  const { sub, args } = call;
  const gpgSign = (arg: string): boolean =>
    arg === '--gpg-sign' || arg.startsWith('--gpg-sign=') || hasShortFlag(arg, 'S', 'mFCct');
  if (SIGNING_SUBS.has(sub) && args.some(gpgSign)) {
    return `signature de commit refusée (git ${sub} -S / --gpg-sign) : D-14`;
  }
  const tagSigns = (arg: string): boolean =>
    arg === '--sign' ||
    arg.startsWith('--local-user') ||
    hasShortFlag(arg, 's', 'mFu') ||
    hasShortFlag(arg, 'u', 'mF');
  if (sub === 'tag' && args.some(tagSigns)) {
    return 'signature de tag refusée (D-14)';
  }
  return undefined;
}

function commitDenial(call: GitCall): Denial {
  const { sub, args } = call;
  if (sub !== 'commit' && sub !== 'commit-tree') {
    return undefined;
  }
  if (args.some((arg) => arg === '--no-verify' || hasShortFlag(arg, 'n', 'mFCct'))) {
    return 'git commit --no-verify / -n contourne les hooks';
  }
  if (args.some((arg) => APPROVAL_SUBJECT.test(arg))) {
    return "commit d'approbation « gate-approval: » réservé à l'humain (D-14)";
  }
  return undefined;
}

function targetsDefaultBranch(spec: string): boolean {
  const destination = (spec.split(':').pop() ?? '')
    .replace(/^\+/, '')
    .replace(/^refs\/heads\//, '');
  return DEFAULT_BRANCHES.has(destination);
}

function pushDenial(args: readonly string[]): Denial {
  const forced = args.some(
    (arg) =>
      arg.startsWith('--force') ||
      arg === '--mirror' ||
      arg === '--all' ||
      hasShortFlag(arg, 'f', 'o'),
  );
  if (forced) {
    return 'git push --force / --mirror / --all refusé';
  }
  const positionals = nonOptions(args);
  if (positionals.some((spec) => spec.startsWith('+'))) {
    return "git push d'une référence forcée (+refspec) refusé";
  }
  return positionals.some(targetsDefaultBranch)
    ? "push vers la branche par défaut : réservé à l'humain (passer par une PR)"
    : undefined;
}

/** Fichiers visés par `git checkout -- f`, `git restore f`, `git rm f`, `git mv a b`. */
function pathTargets(call: GitCall): string[] {
  const { sub, args } = call;
  if (sub === 'restore' || PATH_WRITING_SUBS.has(sub)) {
    return nonOptions(args);
  }
  if (sub !== 'checkout') {
    return [];
  }
  const separator = args.indexOf('--');
  if (separator !== -1) {
    return args.slice(separator + 1);
  }
  return nonOptions(args).slice(1);
}

function configDenial(call: GitCall): Denial {
  const entry = [...call.configs, ...(call.sub === 'config' ? call.args : [])].find((item) =>
    FORBIDDEN_CONFIG.test(item),
  );
  return entry === undefined ? undefined : `configuration git interdite : ${entry}`;
}

/** Refus propres à `git` ; `globs` et `cwd` servent aux écritures de fichiers. */
export function gitDenial(
  words: readonly string[],
  globs: readonly string[],
  cwd: string | undefined,
): Denial {
  const call = parseGit(words);
  const early = configDenial(call) ?? signingDenial(call) ?? commitDenial(call);
  if (early !== undefined) {
    return early;
  }
  if (call.sub === 'push') {
    return pushDenial(call.args);
  }
  const hit = pathTargets(call).find((target) =>
    touchesProtected(target, globs, cwd, PATH_WRITING_SUBS.has(call.sub)),
  );
  return hit === undefined ? undefined : `git ${call.sub} sur un chemin protégé : ${hit}`;
}
