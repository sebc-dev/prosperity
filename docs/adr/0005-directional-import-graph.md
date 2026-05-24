# Graphe d'import directionnel + surface publique par module

La règle `Independence` proposée dans la stratégie de test (§4.3) interdisait tout import croisé entre les 10 modules backend, mais cette règle est intenable dès les premiers développements réels (`debts` lit `transactions`+`budget`, `forecasting` lit `transactions`+`accounts`, `mcp` lit tout, etc.). Le passage à un événementiel intégral est trop coûteux pour un solo dev. Nous décidons d'organiser les modules en **graphe directionnel acyclique** (bas en haut : `shared/` → `auth` → `accounts` → `{transactions, budget, banking}` → `{reconciliation, forecasting, debts, notifications}` → `mcp`), et de matérialiser la frontière d'import par un fichier `public.py` par module qui ré-exporte la surface publique ; les internals (`service.py`, `models.py`, `domain.py`, `repository.py`) sont privés cross-module.

Pour `notifications`, qui serait sinon importé "vers le bas" par les modules métier publiant des notifications, nous introduisons un **mini-bus in-process synchrone** (`shared/events.py`) : les modules métier publient des `DomainEvent` typés sans importer `notifications`, qui s'abonne. Pas de bus distribué, pas d'eventual consistency — dispatch synchrone dans la même transaction DB.

## Considered Options

- **Tout événementiel** : bus + sérialisation + traçage des chaînes + tests de scénarios cross-module → overkill solo.
- **Indépendance par migration vers `shared/`** : produit un `shared/` obèse qui devient le god module → anti-pattern.
- **Graphe directionnel + public surface (retenu)** : équilibre entre traçabilité des dépendances et coût d'implémentation.

## Consequences

- import-linter contracts à écrire : un contrat `layers` qui matérialise le graphe, un contrat `forbidden` qui interdit l'import des internals cross-module, un contrat `forbidden` qui isole `shared/` des modules.
- Chaque module a un `public.py` rédigé explicitement — ce qui force à penser sa surface API avant d'écrire les internals.
- Les chaînes d'events traversent rarement plus d'un module ; la traçabilité reste lisible. Si une chaîne devient longue, c'est un signal de mauvais découpage à examiner.
- La stratégie de test (§4.3) doit remplacer la règle `Independence` par les trois contrats `layers` + `forbidden internals` + `shared isolé`. Document à amender.
- Décision dépendante de l'ADR 0004 (MCP comme module sommet du graphe).
