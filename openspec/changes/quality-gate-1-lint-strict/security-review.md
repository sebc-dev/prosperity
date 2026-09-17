Pas d'impact sécurité.

Le change n'ajoute ni entrée externe, ni endpoint, ni permission, ni traitement de données ; il ajoute des dépendances de **développement** (`eslint-plugin-sonarjs`, `eslint-plugin-jsx-a11y`, `eslint-plugin-boundaries`, `eslint-import-resolver-typescript`, `eslint-plugin-react-hooks` ≥ 6, `deptry`), jamais chargées en production. Seule attention : les figer par version exacte dans `package-lock.json` / `uv.lock` (chaîne d'approvisionnement), comme toute dépendance du dépôt.
