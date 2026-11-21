/**
 * Lecture de la politique supply-chain de `pnpm-workspace.yaml` (clés de premier
 * niveau, sections `clé:` suivies d'entrées indentées, listes en ligne) et
 * détection de tout affaiblissement entre une base et une tête.
 */
interface Policy {
  scalars: Map<string, string>;
  groups: Map<string, Map<string, string>>;
}

const STRICT_FLAGS = ['minimumReleaseAgeStrict', 'blockExoticSubdeps', 'strictDepBuilds'];
const ADDITIVE_LISTS = ['minimumReleaseAgeExclude', 'trustPolicyExclude', 'onlyBuiltDependencies'];

function unquote(text: string): string {
  const trimmed = text.trim();
  const quote = trimmed[0];
  const quoted = (quote === '"' || quote === "'") && trimmed.length >= 2 && trimmed.endsWith(quote);
  return quoted ? trimmed.slice(1, -1) : trimmed;
}

function stripComment(line: string): string {
  const hash = line.search(/(?:^|\s)#/);
  return hash === -1 ? line : line.slice(0, hash);
}

function splitPair(text: string): [string, string] {
  const cut = text.indexOf(':');
  return cut === -1
    ? [unquote(text), '']
    : [unquote(text.slice(0, cut)), unquote(text.slice(cut + 1))];
}

function groupEntry(text: string): [string, string] {
  return text.startsWith('- ') ? [unquote(text.slice(2)), 'listed'] : splitPair(text);
}

function inlineList(value: string): string[] | undefined {
  if (!value.startsWith('[') || !value.endsWith(']')) {
    return undefined;
  }
  return value
    .slice(1, -1)
    .split(',')
    .map(unquote)
    .filter((item) => item !== '');
}

/** Ouvre une clé de premier niveau ; renvoie la section à remplir si elle est en bloc. */
function openTopLevel(policy: Policy, line: string): Map<string, string> | undefined {
  const [key, value] = splitPair(line);
  if (value === '') {
    const group = new Map<string, string>();
    policy.groups.set(key, group);
    return group;
  }
  policy.scalars.set(key, value);
  const items = inlineList(value);
  if (items !== undefined) {
    policy.groups.set(key, new Map(items.map((item) => [item, 'listed'])));
  }
  return undefined;
}

function parsePolicy(text: string): Policy {
  const policy: Policy = { scalars: new Map(), groups: new Map() };
  let current: Map<string, string> | undefined;
  for (const raw of text.split(/\r?\n/)) {
    const line = stripComment(raw).trimEnd();
    if (line.trim() === '') {
      continue;
    }
    if (/^\s/.test(line)) {
      const [name, value] = groupEntry(line.trim());
      current?.set(name, value);
    } else {
      current = openTopLevel(policy, line);
    }
  }
  return policy;
}

function entriesOf(policy: Policy, key: string): string[] {
  const group = policy.groups.get(key);
  if (group !== undefined) {
    return [...group.keys()];
  }
  const scalar = policy.scalars.get(key);
  return scalar === undefined || scalar === '' ? [] : [scalar];
}

function ageWeakened(base: Policy, head: Policy): string[] {
  const before = Number.parseInt(base.scalars.get('minimumReleaseAge') ?? '', 10);
  const after = Number.parseInt(head.scalars.get('minimumReleaseAge') ?? '', 10);
  if (Number.isNaN(before) || (!Number.isNaN(after) && after >= before)) {
    return [];
  }
  return [
    `minimumReleaseAge ${String(before)} remplacé par ${Number.isNaN(after) ? 'absent' : String(after)}`,
  ];
}

function flagsWeakened(base: Policy, head: Policy): string[] {
  return STRICT_FLAGS.filter(
    (key) => base.scalars.get(key) === 'true' && head.scalars.get(key) !== 'true',
  ).map((key) => `${key} n'est plus à true`);
}

function trustWeakened(base: Policy, head: Policy): string[] {
  const before = base.scalars.get('trustPolicy');
  const after = head.scalars.get('trustPolicy');
  return before !== undefined && before !== after
    ? [`trustPolicy « ${before} » remplacée par « ${after ?? 'absent'} »`]
    : [];
}

function listsWeakened(base: Policy, head: Policy): string[] {
  return ADDITIVE_LISTS.flatMap((key) => {
    const known = new Set(entriesOf(base, key));
    return entriesOf(head, key)
      .filter((entry) => !known.has(entry))
      .map((entry) => `${key} : entrée ajoutée « ${entry} »`);
  });
}

function buildsWeakened(base: Policy, head: Policy): string[] {
  const before = base.groups.get('allowBuilds');
  const allowed = [...(head.groups.get('allowBuilds') ?? [])]
    .filter(([name, value]) => value === 'true' && before?.get(name) !== 'true')
    .map(([name]) => `allowBuilds : « ${name} » autorisé à exécuter ses scripts`);
  const all = head.scalars.get('dangerouslyAllowAllBuilds') === 'true';
  const wasAll = base.scalars.get('dangerouslyAllowAllBuilds') === 'true';
  return all && !wasAll ? [...allowed, 'dangerouslyAllowAllBuilds passé à true'] : allowed;
}

/** Une phrase par affaiblissement de la politique entre la base et la tête. */
export function policyWeakenings(baseText: string, headText: string): string[] {
  const base = parsePolicy(baseText);
  const head = parsePolicy(headText);
  return [
    ...ageWeakened(base, head),
    ...flagsWeakened(base, head),
    ...trustWeakened(base, head),
    ...listsWeakened(base, head),
    ...buildsWeakened(base, head),
  ];
}
