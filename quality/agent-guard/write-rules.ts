import { normalize } from 'node:path/posix';
import { isProtected } from '../protected-paths.ts';

/** Raison d'un refus ; `undefined` quand la règle ne s'applique pas. */
export type Denial = string | undefined;

const GIT_HOOKS = '.git/hooks';
const GLOB_START = /[*?[{]/;

/** Arguments qui ne sont pas des options. */
export function nonOptions(args: readonly string[]): string[] {
  return args.filter((arg) => !arg.startsWith('-'));
}

/**
 * Vrai si le cluster d'options courtes (`-nm`) contient `letter` avant une option
 * qui consomme le reste du mot comme valeur (`-mfinal` : « final » est un message).
 */
export function hasShortFlag(arg: string, letter: string, valueFlags: string): boolean {
  if (!/^-[A-Za-z]/.test(arg)) {
    return false;
  }
  for (const char of arg.slice(1)) {
    if (char === letter) {
      return true;
    }
    if (valueFlags.includes(char)) {
      return false;
    }
  }
  return false;
}

function normalizeTarget(raw: string, cwd: string | undefined): string {
  // Un motif fait de jokers et de points (`*`, `.`, `./*`) désigne la racine du dépôt.
  if (/^[*?./]*$/.test(raw)) {
    return '';
  }
  let path = raw.replace(/[*?]/g, 'x');
  if (cwd !== undefined && (path === cwd || path.startsWith(`${cwd}/`))) {
    path = path.slice(cwd.length).replace(/^\/+/, '');
  }
  const clean = normalize(path === '' ? '.' : path).replace(/\/$/, '');
  return clean === '.' ? '' : clean.replace(/^\.\//, '');
}

function literalPrefix(glob: string): string {
  const cut = glob.search(GLOB_START);
  return cut === -1 ? glob : glob.slice(0, cut);
}

/**
 * Vrai si écrire sur `raw` touche un chemin protégé. Avec `parents`, un dossier qui
 * contient un chemin protégé (`rm -rf .claude`) compte aussi, ainsi que la racine.
 */
export function touchesProtected(
  raw: string,
  globs: readonly string[],
  cwd: string | undefined,
  parents: boolean,
): boolean {
  const path = normalizeTarget(raw, cwd);
  if (path === GIT_HOOKS || path.startsWith(`${GIT_HOOKS}/`)) {
    return true;
  }
  if (path !== '' && (isProtected(path, globs) || isProtected(`${path}/_`, globs))) {
    return true;
  }
  return (
    parents && (path === '' || globs.some((glob) => literalPrefix(glob).startsWith(`${path}/`)))
  );
}

function inPlaceTargets(args: readonly string[]): string[] {
  const inPlace = args.some(
    (arg) => arg === '--in-place' || arg.startsWith('--in-place=') || hasShortFlag(arg, 'i', 'ef'),
  );
  return inPlace ? nonOptions(args) : [];
}

function awkTargets(args: readonly string[]): string[] {
  const index = args.indexOf('-i');
  return index !== -1 && args[index + 1] === 'inplace' ? nonOptions(args) : [];
}

function destination(args: readonly string[]): string[] {
  const direct = args.find((arg) => arg.startsWith('--target-directory='));
  return direct === undefined ? nonOptions(args).slice(-1) : [direct.split('=')[1] ?? ''];
}

function ddTargets(args: readonly string[]): string[] {
  return args.filter((arg) => arg.startsWith('of=')).map((arg) => arg.slice(3));
}

interface Extractor {
  targets: (args: readonly string[]) => string[];
  parents: boolean;
}

const EXTRACTORS = new Map<string, Extractor>([
  ['sed', { targets: inPlaceTargets, parents: false }],
  ['perl', { targets: inPlaceTargets, parents: false }],
  ['awk', { targets: awkTargets, parents: false }],
  ['gawk', { targets: awkTargets, parents: false }],
  ['tee', { targets: nonOptions, parents: false }],
  ['truncate', { targets: nonOptions, parents: false }],
  ['dd', { targets: ddTargets, parents: false }],
  ['cp', { targets: destination, parents: false }],
  ['ln', { targets: destination, parents: false }],
  ['install', { targets: destination, parents: false }],
  ['mv', { targets: nonOptions, parents: true }],
  ['rm', { targets: nonOptions, parents: true }],
  ['rmdir', { targets: nonOptions, parents: true }],
  ['unlink', { targets: nonOptions, parents: true }],
  ['shred', { targets: nonOptions, parents: true }],
]);

/** Commandes d'écriture (`sed -i`, `tee`, `mv`, `cp`, `rm`…) dont une cible est protégée. */
export function writeCommandDenial(
  name: string,
  args: readonly string[],
  globs: readonly string[],
  cwd: string | undefined,
): Denial {
  const extractor = EXTRACTORS.get(name);
  if (extractor === undefined) {
    return undefined;
  }
  const hit = extractor
    .targets(args)
    .find((target) => touchesProtected(target, globs, cwd, extractor.parents));
  return hit === undefined ? undefined : `écriture shell (${name}) vers un chemin protégé : ${hit}`;
}

/** Redirections `>`/`>>` vers un chemin protégé. */
export function redirectDenial(
  writes: readonly string[],
  globs: readonly string[],
  cwd: string | undefined,
): Denial {
  const hit = writes
    .filter((target) => !/^[0-9-]*$/.test(target) && target !== '/dev/null')
    .find((target) => touchesProtected(target, globs, cwd, false));
  return hit === undefined ? undefined : `redirection vers un chemin protégé : ${hit}`;
}
