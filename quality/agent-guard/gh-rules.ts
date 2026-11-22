import type { Denial } from './write-rules.ts';

// Groupes `gh` réservés à l'humain : labels (barrière de l'approbation par label, D-03 et D-15),
// secrets, variables, clés du compte (hygiène).
const DENIED_GROUPS = new Set(['label', 'secret', 'variable', 'ssh-key', 'gpg-key']);
const REPO_WRITE_VERBS = new Set([
  'edit',
  'delete',
  'rename',
  'archive',
  'unarchive',
  'deploy-key',
]);
const LABEL_FLAG = /^--(?:add-|remove-)?label(?:=|$)/;
const FIELD_FLAG = /^(?:-[fF](?:[^-]|$)|--field(?:=|$)|--raw-field(?:=|$)|--input(?:=|$))/;

interface GhCall {
  group: string;
  verb: string;
  args: string[];
}

function parseGh(words: readonly string[]): GhCall {
  const args = words.slice(1);
  const positionals: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index] ?? '';
    if (arg === '-R' || arg === '--repo') {
      index += 1;
    } else if (!arg.startsWith('-')) {
      positionals.push(arg);
    }
  }
  return { group: positionals[0] ?? '', verb: positionals[1] ?? '', args };
}

function apiMethod(args: readonly string[]): string | undefined {
  for (const [index, arg] of args.entries()) {
    if (arg === '-X' || arg === '--method') {
      return args[index + 1];
    }
    if (arg.startsWith('--method=')) {
      return arg.slice('--method='.length);
    }
    if (arg.startsWith('-X')) {
      return arg.slice(2);
    }
  }
  return undefined;
}

/** `gh api` : lecture seule, jamais de champ (implique une écriture), jamais les clés du compte. */
function apiDenial(args: readonly string[]): Denial {
  const method = apiMethod(args);
  if (method !== undefined && method.toUpperCase() !== 'GET') {
    return `gh api avec la méthode ${method} refusé (écriture réservée à l'humain)`;
  }
  if (args.some((arg) => FIELD_FLAG.test(arg))) {
    return 'gh api avec un champ (-f/-F/--field/--input) implique une écriture : refusé';
  }
  if (args.some((arg) => arg === 'graphql' || arg.endsWith('/graphql'))) {
    return 'gh api graphql refusé (mutations possibles)';
  }
  return args.some((arg) => arg.includes('keys'))
    ? "gh api sur les clés du compte refusé : hygiène, réservé à l'humain (l'approbation est le label de D-15)"
    : undefined;
}

function labelDenial(call: GhCall): Denial {
  const { group, verb, args } = call;
  const edits = (group === 'pr' || group === 'issue') && (verb === 'create' || verb === 'edit');
  if (edits && args.some((arg) => LABEL_FLAG.test(arg) || arg === '-l')) {
    return "pose ou retrait de label refusé : l'approbation par label appartient à l'humain (D-03, D-15)";
  }
  return undefined;
}

function reservedDenial(call: GhCall): Denial {
  const { group, verb, args } = call;
  const reserved: [boolean, string][] = [
    [group === 'pr' && verb === 'merge', "fusion de PR réservée à l'humain"],
    [group === 'pr' && verb === 'review', "revue de PR réservée à l'humain"],
    [group === 'repo' && REPO_WRITE_VERBS.has(verb), "réglages du dépôt réservés à l'humain"],
    [
      group === 'workflow' && (verb === 'disable' || verb === 'enable'),
      "activation de workflow réservée à l'humain",
    ],
    [group === 'auth' && verb === 'token', 'gh auth token refusé'],
    [group === 'auth' && args.includes('--show-token'), 'gh auth --show-token refusé'],
  ];
  return reserved.find(([applies]) => applies)?.[1];
}

/** Refus propres à `gh` (labels, fusion, revue, réglages, secrets, API en écriture, clés). */
export function ghDenial(words: readonly string[]): Denial {
  const call = parseGh(words);
  if (call.group === 'api') {
    return apiDenial(call.args);
  }
  if (DENIED_GROUPS.has(call.group)) {
    return `gh ${call.group} réservé à l'humain`;
  }
  return reservedDenial(call) ?? labelDenial(call);
}
