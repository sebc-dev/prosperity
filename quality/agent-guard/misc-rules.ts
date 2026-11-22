import { nonOptions } from './write-rules.ts';
import type { Denial } from './write-rules.ts';

const PACKAGE_MUTATIONS = new Set([
  'add',
  'remove',
  'rm',
  'uninstall',
  'un',
  'update',
  'up',
  'upgrade',
  'patch',
  'patch-commit',
  'link',
]);
const INSTALL_VERBS = new Set(['install', 'i']);

/** `ssh-keygen`, `ssh-add` : ni signature ni clé pour l'agent (hygiène : l'approbation est le label de D-15). */
export function sshDenial(name: string): Denial {
  return `${name} refusé : l'agent ne touche ni aux clés ni à la signature (hygiène : l'approbation est le label de D-15)`;
}

export function lefthookDenial(args: readonly string[]): Denial {
  return args[0] === 'uninstall' ? 'lefthook uninstall désarme les hooks' : undefined;
}

/** `curl` / `wget` vers l'API GitHub : le jeton de l'humain ne sert pas à écrire par ce canal. */
export function downloadDenial(args: readonly string[]): Denial {
  return args.some((arg) => arg.includes('api.github.com'))
    ? "requête vers api.github.com refusée (écriture par API réservée à l'humain)"
    : undefined;
}

/** Ajouts et retraits de dépendances : validés par un humain (label `deps-approved`, D-15). */
export function packageDenial(name: string, args: readonly string[]): Denial {
  const [verb, ...rest] = nonOptions(args);
  if (verb === undefined) {
    return undefined;
  }
  const installsPackage = INSTALL_VERBS.has(verb) && rest.length > 0;
  return PACKAGE_MUTATIONS.has(verb) || installsPackage
    ? `${name} ${verb} refusé : dépendances validées par un humain`
    : undefined;
}
