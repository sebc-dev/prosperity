# Architecture — table des invariants

Référent de la **dimension architecture** de la review (`review-context` la résout une fois,
`architecture-reviewer` la confronte au diff). Une ligne = un invariant **opposable** : sa source est
un ADR de `docs/adr/`, et le diff qui le viole est bloquant sauf dérogation déclarée au ticket.

Ce fichier ne redit pas le *pourquoi* — il est dans l'ADR cité. La vision d'ensemble (modules
cibles, graphe complet à 12 modules, frontend) reste dans [`Architectures BS.md`](./Architectures%20BS.md).
Ici, l'état **matérialisé dans le code** : les 8 modules présents et les contrats `.importlinter`
qui les gardent.

## Frontières et sens de dépendance (backend)

Graphe en couches tel que `.importlinter` le vérifie aujourd'hui (haut = dépend de, bas = dépendu) :

```
sync | sse
debts
banking | transactions | budget
accounts
auth
shared
```

| Id | Invariant | ADR | Vérifié par |
|---|---|---|---|
| A01 | Un module n'importe que des modules **strictement en dessous** dans le graphe ; jamais un pair de la même couche, jamais vers le haut. | [0005](./adr/0005-directional-import-graph.md) | `.importlinter` contrat 1 (`layers`) |
| A02 | L'import cross-module passe **uniquement** par `public.py`. `service`, `models`, `domain`, `repository`, `transports`, `handlers` d'un autre module sont privés. | [0005](./adr/0005-directional-import-graph.md) | contrats `2-<module>` (`forbidden`), un par module |
| A03 | `backend.shared` n'importe **rien** de `backend.modules.*`. Tout module peut importer `shared`. | [0005](./adr/0005-directional-import-graph.md) | contrat 3 |
| A04 | Un module bas communique vers le haut par un `DomainEvent` publié sur `shared/events.py` (bus in-process synchrone, même transaction DB) — jamais par un import. | [0005](./adr/0005-directional-import-graph.md) | contrat 1 (un import montant casse les couches) |
| A05 | Les `Depends` RBAC (`require_admin`, `require_member`, `get_current_user`) vivent dans `auth` et sont exposés par `auth.public` — pas dans `shared` (A03 l'interdit). | [0005](./adr/0005-directional-import-graph.md) | contrat 3 + revue |
| A06 | `backend.transports` est la **racine de composition** des flux cross-module : elle consomme les `public` de tous, et **n'est importée par aucun** module ni par `shared`. | [0005](./adr/0005-directional-import-graph.md) (pairs interdits → composition au-dessus) | contrat 6 |
| A07 | Seul `banking.service.polling` importe `banking.providers` (le `BankingProvider` externe). Tout autre consommateur passe par `BankingReader` via `banking.public`. Un tool MCP ne déclenche jamais un appel synchrone au provider. | [0009](./adr/0009-banking-provider-reader-split.md) | contrat 4 |
| A08 | `debts.domain` reste **pur** : il reçoit des scalaires, n'importe pas `Transaction`. | [0002](./adr/0002-debts-as-server-projection.md) (refined-by E09) | contrat 2-debts + revue |
| A09 | Tout nouveau répertoire sous `backend/modules/` entre dans `.importlinter` (couche + contrat `2-<module>` + `source_modules` du contrat 6) **dans le même diff**. | [0005](./adr/0005-directional-import-graph.md) | `tests/unit/test_importlinter_coverage.py` |

## Artefacts prescrits et invariants de données

| Id | Invariant | ADR |
|---|---|---|
| D01 | `Transaction` est immutable à `confirmed` : splits et montant gelés ; correction = `void` + nouvelle transaction. Seuls `category_id`, `tags`, `description`, `debt_generation_override`, `share_request` restent éditables. | [0001](./adr/0001-transaction-aggregate-immutable.md) |
| D02 | Les dettes sont une **projection serveur** matérialisée par `debts.service` à chaque write de transaction ; lecture seule côté client. Le client n'écrit jamais dans `debts`. | [0002](./adr/0002-debts-as-server-projection.md) |
| D03 | Quatre familles de buckets PowerSync (`user_personal_*`, `account_shared_*`, `user_debt_*`, `household`). Les tables server-only (`pending_actions`, `audit_logs`, `pat_tokens`, `users` PII, `invitations`, `device_tokens`, `sync_request_log`, `auth_challenges`) ne sont **jamais** synchronisées. | [0003](./adr/0003-powersync-bucket-design.md) |
| D04 | Une mutation client passe par le **write upload handler** de `sync` : séquence stricte auth → idempotence (`client_request_id`) → validation → write → projections → events → commit → log → ack, dans **une** transaction DB. Pas de chemin d'écriture parallèle. | [0014](./adr/0014-sync-module-and-write-upload-handler.md) |
| D05 | `Money(amount_cents, currency)` est le seul type monétaire ; aucune arithmétique cross-devise ; V1 verrouillée EUR par `household.base_currency`. | [0008](./adr/0008-mono-currency-v1-via-household-pin.md) |
| D06 | Les services sont **transaction-agnostic** : `shared.db.get_db` seul commite/rollback, les routes ne commitent jamais. Unique exception : effet de bord security-critical commité dans le service **avant** `raise`. | [0015](./adr/0015-commit-inside-service-for-security-side-effects.md) |
| D07 | `household` est un singleton à UUID fixe ; les invitations sont des tokens hashés, rôle figé `member`. | [0010](./adr/0010-household-singleton-and-invitation-flow.md) |
| D08 | Un `Settlement` est une entité multi-lignes ; `Debt` ne porte aucun état de règlement. | [0011](./adr/0011-settlement-as-multi-line-entity.md) |
| D09 | Le rôle d'une jambe de `Split` (dépense confirmable vs consommation budget) est un marqueur structurel, pas une déduction. | [0017](./adr/0017-confirmable-expense-vs-budget-consumption.md) |

Les invariants de **sécurité** (SSE via JWT short-lived [0012](./adr/0012-sse-auth-via-short-lived-query-token.md),
2FA/step-up [0013](./adr/0013-2fa-totp-and-pat-stepup.md), claims `aud`/`iss`
[0016](./adr/0016-jwt-aud-iss-claims.md)) sont le référent de la dimension **sécurité**, pointés par
`openspec/config.yaml` — ils ne sont pas dupliqués ici.

## Modules cibles non encore présents

`reconciliation`, `forecasting`, `savings`, `notifications`, `mcp` sont décrits dans
`Architectures BS.md` §4–5 et par les ADR [0004](./adr/0004-mcp-as-module.md),
[0006](./adr/0006-reconciliation-as-distinct-entity.md),
[0007](./adr/0007-recurring-generation-server-cron.md). À leur arrivée, A09 s'applique : la couche
cible est celle du graphe §5 (`reconciliation | forecasting | debts | notifications` au-dessus de
`banking | transactions | budget` ; `sync` puis `mcp` au sommet).

## Frontend — repères, non contraignants

Aucun ADR ne contraint la structure `client/src/` ; le repère est
[`Architectures BS.md` §7](./Architectures%20BS.md) : `app/` (router, providers), `pages/` (un fichier
= une route), `features/` (interactions complètes), `components/business/` et `components/ui/`
(shadcn généré, ne pas éditer à la main), `lib/` (`powersync`, `drizzle`, `api` typé OpenAPI, `sse`),
`hooks/`, `types/` (générés). **Pas** de couche `entities/`, pas de séparation
domain/application/infrastructure/ui. Un écart est une suggestion, pas un bloquant.
