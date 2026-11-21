import { isRecord } from './tools.ts';

export interface DepChange {
  name: string;
  from?: string;
  to?: string;
  kind: 'dependency-added' | 'dependency-changed' | 'dependency-removed' | 'transitive-added';
}

export interface DependencySnapshot {
  packageJson: string;
  lockfile: string;
}

interface ManifestEntry {
  name: string;
  version: string;
}

const DEP_SECTIONS = [
  'dependencies',
  'devDependencies',
  'optionalDependencies',
  'peerDependencies',
] as const;
const PACKAGES_HEADER = /^packages:\s*$/;
const TOP_LEVEL = /^\S/;

function change(kind: DepChange['kind'], name: string, from?: string, to?: string): DepChange {
  return {
    name,
    ...(from === undefined ? {} : { from }),
    ...(to === undefined ? {} : { to }),
    kind,
  };
}

/** `foo@<2` donne `foo` ; `parent>@scope/child` donne `@scope/child` : le paquet visé par une surcharge. */
function overrideTarget(key: string): string {
  const segment = key.split('>').pop() ?? key;
  const at = segment.indexOf('@', 1);
  return at > 0 ? segment.slice(0, at) : segment;
}

function addSection(entries: Map<string, ManifestEntry>, section: string, value: unknown): void {
  if (!isRecord(value)) {
    return;
  }
  for (const [key, version] of Object.entries(value)) {
    if (typeof version === 'string') {
      const name = section === 'pnpm.overrides' ? overrideTarget(key) : key;
      entries.set(`${section}:${key}`, { name, version });
    }
  }
}

function manifestEntries(packageJson: string): Map<string, ManifestEntry> {
  const parsed: unknown = JSON.parse(packageJson === '' ? '{}' : packageJson);
  const entries = new Map<string, ManifestEntry>();
  if (!isRecord(parsed)) {
    return entries;
  }
  for (const section of DEP_SECTIONS) {
    addSection(entries, section, parsed[section]);
  }
  const pnpm = parsed['pnpm'];
  addSection(entries, 'pnpm.overrides', isRecord(pnpm) ? pnpm['overrides'] : undefined);
  return entries;
}

function diffManifests(base: string, head: string): DepChange[] {
  const before = manifestEntries(base);
  const after = manifestEntries(head);
  const changes: DepChange[] = [];
  for (const [key, entry] of after) {
    const previous = before.get(key);
    if (previous === undefined) {
      changes.push(change('dependency-added', entry.name, undefined, entry.version));
    } else if (previous.version !== entry.version) {
      changes.push(change('dependency-changed', entry.name, previous.version, entry.version));
    }
  }
  for (const [key, entry] of before) {
    if (!after.has(key)) {
      changes.push(change('dependency-removed', entry.name, entry.version));
    }
  }
  return changes;
}

/** `  nom@1.0.0:` ou `  '@portée/nom@1.0.0':` (exactement deux espaces) : `{ name, version }`. */
function packageKeyOf(line: string): { name: string; version: string } | undefined {
  const text = line.trimEnd();
  if (!text.startsWith('  ') || text.startsWith('   ') || !text.endsWith(':')) {
    return undefined;
  }
  const raw = text.slice(2, -1);
  const unquoted = raw.startsWith("'") && raw.endsWith("'") ? raw.slice(1, -1) : raw;
  const peers = unquoted.indexOf('(');
  const key = peers === -1 ? unquoted : unquoted.slice(0, peers);
  const at = key.lastIndexOf('@');
  return at > 0 ? { name: key.slice(0, at), version: key.slice(at + 1) } : undefined;
}

/** Clés de premier niveau de chaque section `packages:` (un lockfile pnpm peut compter deux documents YAML). */
function lockPackages(lockfile: string): Map<string, Set<string>> {
  const found = new Map<string, Set<string>>();
  let inPackages = false;
  for (const line of lockfile.split(/\r?\n/)) {
    if (PACKAGES_HEADER.test(line)) {
      inPackages = true;
    } else if (TOP_LEVEL.test(line)) {
      inPackages = false;
    } else if (inPackages) {
      const entry = packageKeyOf(line);
      if (entry !== undefined) {
        found.set(entry.name, (found.get(entry.name) ?? new Set<string>()).add(entry.version));
      }
    }
  }
  return found;
}

const joined = (versions: Iterable<string>): string =>
  [...versions].sort((a, b) => a.localeCompare(b)).join(', ');

function diffLockfiles(base: string, head: string, named: ReadonlySet<string>): DepChange[] {
  const before = lockPackages(base);
  const changes: DepChange[] = [];
  const names = [...lockPackages(head)].sort(([a], [b]) => a.localeCompare(b));
  for (const [name, versions] of names) {
    const previous = before.get(name);
    const fresh =
      previous === undefined ? [...versions] : [...versions].filter((v) => !previous.has(v));
    if (named.has(name) || fresh.length === 0) {
      continue;
    }
    changes.push(
      previous === undefined
        ? change('transitive-added', name, undefined, joined(fresh))
        : change('dependency-changed', name, joined(previous), joined(fresh)),
    );
  }
  return changes;
}

/**
 * Différences de dépendances entre deux états : sections de `package.json`, surcharges pnpm, puis
 * noms et versions de paquets du lockfile (un paquet déjà signalé en direct n'est pas redoublé).
 */
export function diffDependencies(base: DependencySnapshot, head: DependencySnapshot): DepChange[] {
  const direct = diffManifests(base.packageJson, head.packageJson);
  const named = new Set(direct.map((entry) => entry.name));
  return [...direct, ...diffLockfiles(base.lockfile, head.lockfile, named)];
}
