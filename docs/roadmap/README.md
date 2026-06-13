# Roadmap — Découpage MVP

> Source de vérité versionnée du découpage en epics, stories et phases.
> Sync vers GitHub Issues fait à la demande via le skill `to-issues` (D3 hybride lazy).
>
> **Docs liés** : [`../../CONTEXT.md`](../../CONTEXT.md), [`../adr/`](../adr/), [`../Architectures BS.md`](../Architectures%20BS.md), [`../Stratégie de tests.md`](../Strat%C3%A9gie%20de%20tests.md), [`../Sans titre.md`](../Sans%20titre.md)

---

## Hiérarchie

| Niveau | Granularité | Durée typique | Livrable |
|---|---|---|---|
| **Epic** | Capacité fonctionnelle ou pilier technique | 1-3 semaines | Fichier `EXX-slug.md` dans ce dossier, issue parente GitHub quand pertinent |
| **Story** | Tranche cohérente avec valeur observable (vertical slice quand possible) | 1-3 jours | Section dans le fichier epic, issue enfant grabbable par Claude Code |
| **Phase** | Unité atomique reviewable en une passe humaine | 2-6 heures | Une PR ciblée, ≤ 400 lignes de diff |

## Règles d'atomicité par phase

1. **Single Responsibility** : une phase fait UNE chose conceptuelle.
2. **Self-contained** : la branche compile, les tests passent, `import-linter` passe. Pas de "à compléter dans la phase suivante" qui casse la CI.
3. **Pas de mix refactor + feature + test** : refactors préparatoires en phases dédiées.
4. **Test-first quand possible** sur les modules à `domain.py` : phase tests avant phase impl — sauf si bundle < 400 lignes.
5. **Migration DB non-triviale = phase dédiée** (avec test Niveau 1 schema check).
6. **Nouvel ADR = phase dédiée** ajoutée avant la phase qui s'appuie dessus.
7. **Documentation inline** : CONTEXT.md update, docstrings, README de module → dans la même PR que le code qu'ils décrivent. Pas de phase "docs" séparée.

## Convention de nommage

- Epic : `EXX-slug.md` (ex. `E01-bootstrap.md`)
- Story ID : `SXX.Y` (ex. `S01.3`)
- Phase ID : `PXX.Y.Z` (ex. `P01.3.2`)

Les IDs sont stables et utilisés dans les noms de branches Git : `branch: SXX.Y-slug` ou `PXX.Y.Z-slug`.

---

## Liste des epics MVP

Ordre topologique. Chaque epic ne démarre qu'après ses dépendances.

| # | Epic | Couvre | Dépend de | Statut |
|---|---|---|---|---|
| [E01](./E01-bootstrap.md) | Backend bootstrap + quality gates | pytest + Hypothesis + testcontainers + import-linter (5 contrats J1) + pre-commit + CI workflows + Alembic init + scaffolding modulaire vide | — | not started |
| [E02](./E02-auth-foundations.md) | Auth foundations | F01 sans PAT ni 2FA (email + Argon2id + JWT + refresh) + `users` server-only | E01 | not started |
| [E03](./E03-household-bootstrap.md) | Household singleton + bootstrap `/setup` | ADR 0010 : table `household` + flow `/setup` lock-after-init + premier admin | E02 | not started |
| [E04](./E04-rbac-invitations.md) | RBAC + invitations | F03 : rôles admin/member + flow invitation token-based (ADR 0010) + audit log admin | E03 | not started |
| [E05](./E05-accounts.md) | Accounts | F02 : comptes personnel + commun + `account_members` + quote-parts | E04 | not started |
| [E06](./E06-categories.md) | Categories hiérarchiques | F08 partie 1 : `Category` + cycle prevention + archive + bucket household | E05 | not started |
| [E07](./E07-transactions.md) | Transactions module | F05 : `Transaction` aggregate immutable (ADR 0001) + splits relationnels + states + Money | E05, E06 | not started |
| [E08](./E08-budgets.md) | Budgets | F08 partie 2 : `Budget` + agrégation hiérarchique + alertes seuils via `shared/events.py` | E07 | not started |
| [E08.5](./E08.5-canonical-expense-reconciliation.md) | Réconciliation dépense confirmable ↔ consommation budget | ADR 0017 : `leg_role` sur `Split` — une dépense confirmable consomme un budget (lève la contradiction E07/E08) | E08 | not started |
| [E09](./E09-debts-foundations.md) | Debts foundations | F09 partie 1 : `Debt` projection (ADR 0002) + `share_request` + dashboard dettes | E05, E07 | not started |
| [E10](./E10-settlements.md) | Settlements | F09 partie 2 : `Settlement` multi-line (ADR 0011) + 3 types + invariants Hypothesis | E09 | not started |
| [E11](./E11-debts-overflow.md) | Debts overflow F10 | `debt_generation_override` + `DebtCalculator` matérialisation excédent | E08.5, E10 | not started |
| [E12](./E12-ofx-import.md) | OFX import | F04 partie 1 : `OFXProvider` + wrapper défensif + preview hybride + `bank_account_external_refs` | E05, E07 | not started |
| [E13](./E13-sync-write-upload-handler.md) | Sync module + write upload handler | ADR 0014 : module `sync` + dispatcher + 10 étapes + idempotence + `WriteResult.error` typé | E07, E09, E11 | done |
| [E14](./E14-frontend-bootstrap.md) | Frontend bootstrap | Capacitor 8 + React 19 + Vite 6 + Drizzle + Tailwind + shadcn scaffolding + PowerSync client setup | E13 | not started |
| [E15](./E15-ui-mvp.md) | UI MVP (~15 écrans) | Login + dashboard solde réel + comptes + transactions + budgets + dettes + settings + invitation accept | E14 | not started |
| [E16](./E16-deployment.md) | Deployment | Podman Quadlet + Caddy + Cloudflare Tunnel + Tailscale + Restic→B2 + runbooks | E15 | not started |
| [E17](./E17-realtime-sse-backend.md) | Realtime backend (SSE) | ADR 0012 : `POST /sse/token` + `GET /sse/stream` + heartbeat 30 s + buffer/resume `Last-Event-ID` | E02, E04 | not started |
| [E18](./E18-devx-ci.md) | DevX / CI (optimisation workflows) | CI path-scopée par périmètre (backend/frontend/docs) + agrégateur de *required check* + parallélisme + cache uv/npm/Docker + runbook | E01 | not started |

> **Hors-séquence** : E17 (backend SSE) a été ajouté après coup — gap découvert à la création des stories E14 (#205-#211). Topologiquement il **précède E14 S14.7** (#211, qui en dépend) ; son numéro ne reflète pas l'ordre d'exécution.
>
> **Transverse** : E18 (DevX/CI) est un epic **outillage** hors séquence fonctionnelle MVP — il optimise les workflows posés par E01 et fournit la structure de gating/cache sur laquelle S14.7 (#211) branchera les jobs frontend.

**Volume estimé** : ~80-120 stories et ~250-400 phases pour le MVP complet.

---

## Statuts possibles

- `not started`
- `in progress` (avec story en cours indiquée)
- `done`
- `blocked` (avec raison)

## Mise à jour

Quand une story / phase change de statut, mettre à jour le tableau dans le fichier epic concerné. La table principale ci-dessus reflète l'état global de chaque epic (résumé).
