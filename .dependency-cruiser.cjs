// Frontières d'architecture (CLAUDE.md § 10.2 « Contrats d'import »), écrites pour la disposition de
// quality/layout.json : les expressions de couche sont lues dans `layout.depcruise`, jamais recopiées ici.
//
// Règle de maintenance (ARCHITECTURE.md) : tout nouveau dossier de module entre dans quality/layout.json
// ET dans ce fichier dans le même diff.
//
// Verdict : `depcruise --output-type json` rend le code 0 même avec des violations ; la gate lit
// `summary.error` et `summary.violations` (quality/checks/arch.ts), jamais le code de sortie.
const { depcruise } = require('./quality/layout.json');

module.exports = {
  forbidden: [
    {
      name: 'no-circular',
      comment: 'Aucun cycle d’imports.',
      severity: 'error',
      from: {},
      to: { circular: true },
    },
    {
      name: 'not-to-unresolvable',
      comment: 'Tout import doit se résoudre.',
      severity: 'error',
      from: {},
      to: { couldNotResolve: true },
    },
    {
      name: 'domain-is-pure',
      comment:
        'Le domaine pur (shared, modules/*/domain) n’importe que du domaine pur : ni pg, ni fs, ni module npm. Les imports de types seuls sont permis.',
      severity: 'error',
      from: { path: depcruise.pure },
      to: { pathNot: depcruise.pure, dependencyTypesNot: ['type-only'] },
    },
    {
      name: 'mcp-tools-no-db',
      comment:
        'Un outil MCP n’atteint jamais la base ni un adaptateur de module : il passe par la couche application (le filtre par membre).',
      severity: 'error',
      from: { path: depcruise.mcp },
      to: { path: [depcruise.moduleAdapters, depcruise.db] },
    },
    {
      name: 'cross-module-public-only',
      comment: 'Un module n’atteint un autre module que par son public.ts.',
      severity: 'error',
      from: { path: '^src/modules/([^/]+)/' },
      to: {
        path: '^src/modules/([^/]+)/',
        pathNot: ['^src/modules/$1/', '^src/modules/[^/]+/public\\.ts$'],
      },
    },
    {
      name: 'db-access-restricted',
      comment:
        'src/db n’est importé que depuis les adaptateurs db des modules, la composition et le worker.',
      severity: 'error',
      from: { path: '^src/', pathNot: [depcruise.dbAllowedFrom, depcruise.db] },
      to: { path: depcruise.db },
    },
    {
      name: 'no-dev-deps-in-src',
      comment: 'Le code de src/ ne dépend d’aucune devDependency (hors tests, exclus).',
      severity: 'error',
      from: { path: '^src/' },
      to: { dependencyTypes: ['npm-dev'] },
    },
  ],
  options: {
    tsConfig: { fileName: 'tsconfig.json' },
    tsPreCompilationDeps: true,
    doNotFollow: { path: 'node_modules' },
    exclude: { path: '\\.test\\.ts$' },
    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default', 'types'],
    },
  },
};
