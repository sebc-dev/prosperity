# E05 — Accounts (personnels + communs + quote-parts)

> **Durée estimée** : 4-5 jours
> **Statut** : not started
> **Dépend de** : E04
> **Bloque** : E07, E09, E12 (banking), E15 (UI accounts)
> **ADRs activés** : 0008 (validation `account.currency == household.base_currency`)

---

## Objectif

Implémenter F02 : comptes personnels (un seul owner, étanche admin compris) + comptes communs (`account_members` avec `default_share_ratio`). Validation devise vs `household.base_currency`. Suppression d'un user → comptes deviennent inaccessibles (audit only) ou flow de transfert de propriété.

Livrable agrégé : un user peut créer son compte personnel, un admin (en tant que future propriétaire) peut créer un compte commun avec lui-même + d'autres members + quote-parts, et chacun voit uniquement ce dont il est membre.

---

## Stories

### S05.1 — Modèle `Account` + types

**Livrable observable** : table `accounts` créée, factory + tests.

| Phase | Description | Diff |
|---|---|---|
| **P05.1.1** | Modèle `Account` dans `modules/accounts/models.py` : `id`, `household_id` FK (toujours singleton), `name`, `type` (Literal['courant','livret','epargne','especes','credit']), `currency` ISO 4217, `owner_id` FK `ON DELETE RESTRICT` NULL (personnel), `created_at`, `archived_at` NULL. **`bank_link_id` reporté à E12** (FK vers une table qui n'existe pas encore ⇒ migration impossible en E05). Pas de constraint "owner XOR members" en SQL — vérifié au service | ~110 |
| **P05.1.2** | Modèle `AccountMember` : `id`, `account_id` FK `ON DELETE CASCADE`, `user_id` FK `ON DELETE RESTRICT`, `default_share_ratio` (`Numeric(5,4)` → `Decimal`, sum = 1 par account vérifié au service), `joined_at`. Unique index `(account_id, user_id)` + index FK | ~90 |
| **P05.1.3** | Migration `0007_accounts.py` (`down_revision = "0006"`). Test niveau 1 schema check. Test : on ne peut pas supprimer un user qui a des `owner_id` (`ON DELETE RESTRICT`) — décision : on garde le user disabled (audit), on ne supprime pas | ~120 |

---

### S05.2 — Validation devise + invariant propriété

**Livrable observable** : `accounts.service.validate_creation()` rejette devise ≠ household, rejette compte sans owner ET sans members, rejette quote-parts ne sommant pas à 1.

| Phase | Description | Diff |
|---|---|---|
| **P05.2.1** | `accounts/domain.py` : `AccountValidator` pur — règles `currency == household.base_currency`, `(owner_id IS NOT NULL) XOR (len(members) ≥ 2)`, `sum(member.default_share_ratio) == Decimal("1.0000")` (**Decimal exact**, pas de conversion float ni tolérance — la colonne est `Numeric(5,4)`). Tests example + Hypothesis | ~150 |
| **P05.2.2** | `accounts.service` : `create_personal(owner_id, ...)`, `create_shared(members_with_ratios, ...)`. Chaque crée Account + AccountMember(s) en transaction DB unique. Tests intégration | ~180 |

---

### S05.3 — Routes accounts (RBAC)

**Livrable observable** : `POST /accounts`, `GET /accounts` (filtré au user), `GET /accounts/{id}`, `PATCH /accounts/{id}` (membres uniquement), `DELETE /accounts/{id}` → archivage.

| Phase | Description | Diff |
|---|---|---|
| **P05.3.1** | Schemas Pydantic `AccountCreatePersonal`, `AccountCreateShared`, `AccountResponse`, `AccountMemberInput`. Route `POST /accounts` (deux endpoints distincts `/accounts/personal` et `/accounts/shared` pour éviter polymorphisme Pydantic complexe). Tests httpx | ~180 |
| **P05.3.2** | Route `GET /accounts` qui filtre selon le user authentifié : ses comptes personnels + comptes communs où il est membre. **L'admin n'est PAS exempté** (cf. F03 invariant). Tests : admin ne voit jamais les comptes personnels des autres | ~150 |
| **P05.3.3** | Routes `GET /accounts/{id}` (404 si pas accès même pour admin) + `PATCH` (**`name` uniquement** — `currency` et `type` gelés à la création) + `DELETE` (archivage `archived_at`, pas suppression dure). Tests | ~200 |

---

### S05.4 — `account_members` management + DomainEvents

**Livrable observable** : un membre peut être ajouté/retiré d'un compte commun par un autre membre ; chaque mutation publie un `DomainEvent` typé reçu par un abonné de test.

> **Re-découpée 2 → 3 phases.** Introduit la primitive transverse `shared/events.py` (qui n'existe pas encore) en phase dédiée **avant** son usage. Les `account_member_*` sont des **DomainEvents** (tout membre les déclenche), **pas** des `admin_audit_logs` (réservés aux actes admin).

| Phase | Description | Diff |
|---|---|---|
| **P05.4.1** | Primitive `shared/events.py` : `DomainEvent` (base) + dispatcher **synchrone in-process** `subscribe`/`publish` (même transaction DB, cf. glossaire). Aucun abonné encore. `shared` n'importe rien de `modules.*` (contrat #3). Tests | ~90 |
| **P05.4.2** | Service + routes `POST /accounts/{id}/members` + `DELETE /accounts/{id}/members/{user_id}` + `PATCH /accounts/{id}/members/{user_id}` (édition `default_share_ratio`). Tout membre actuel peut éditer (pas seulement admin). Pas retirer le dernier membre (compte orphelin). Tests | ~200 |
| **P05.4.3** | Émission des DomainEvents `account_member_added`, `account_member_removed`, `share_ratio_updated` depuis le service, dans la même transaction (préparation E08 budgets qui souscriront). Types définis dans `accounts`, publiés via `shared.events`. Tests (spy abonné) | ~80 |

---

### S05.5 — Hypothesis : invariants comptes

**Livrable observable** : property tests passent sur les invariants critiques.

| Phase | Description | Diff |
|---|---|---|
| **P05.5.1** | Strategy `account_with_members_strategy` dans `tests/strategies.py` (gen un compte commun valide avec N members et quote-parts sommant à 1). Property : tout compte créé via strategy passe `AccountValidator`. Property : un account `personal` n'a pas de members. Property : un account `shared` a ≥ 2 members | ~150 |
| **P05.5.2** | Property : modification de `default_share_ratio` d'un member maintient `sum == 1` (forçant un re-balance via le service, sinon erreur). Tests | ~80 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S05.1 (3 phases) | Modèles | 320 | 320 |
| S05.2 (2 phases) | Validation domain | 330 | 650 |
| S05.3 (3 phases) | Routes | 530 | 1180 |
| S05.4 (3 phases) | Members management + events | 370 | 1550 |
| S05.5 (2 phases) | Hypothesis | 230 | 1780 |
| **Total** | **5 stories / 13 phases** | **~1780 lignes** | |

---

## Critères d'acceptation

- [ ] Compte personnel ne peut pas être créé sans owner
- [ ] Compte commun ne peut pas être créé sans ≥ 2 members + sum(ratios) == 1
- [ ] Création d'un compte avec devise ≠ household.base_currency échoue (validation)
- [ ] Admin ne voit pas les comptes personnels des autres users via `GET /accounts` (F03)
- [ ] Suppression d'un compte = archivage (`archived_at` set), pas suppression dure
- [ ] Modification de `default_share_ratio` re-balance ou échoue, jamais ne casse sum=1
- [ ] DomainEvent `account_member_*` publiés via `shared/events.py` (mini-bus synchrone introduit en P05.4.1 — **pas** un `admin_audit_logs`)
- [ ] Coverage `modules/accounts/domain.py` ≥ 90%, service ≥ 75%

---

## Notes pour l'implémenteur

- Les `default_share_ratio` sont stockés en `Decimal(5,4)` (max 0.9999, précision 4 décimales — suffit pour 50/25/25 etc., et évite les float-rounding pénibles).
- Les routes `POST /accounts/personal` et `POST /accounts/shared` sont **distinctes** pour éviter le polymorphisme Pydantic (qui est faisable mais alourdit la doc OpenAPI). Côté UI on choisit le type d'abord, puis le formulaire.
- Quand un user est `disabled` (E04 promotion ou autre flow), ses comptes personnels restent en DB mais deviennent inaccessibles par `GET /accounts`. Pas de transfert auto à un autre user — décision F02 (option : ajouter un flow admin de transfert en V1).
- L'invariant `sum(default_share_ratio) == 1` est vérifié au service, pas en CHECK SQL (CHECK SQL multi-row PostgreSQL = trigger, trop complexe pour ce besoin).

### Deltas de réconciliation (stories #92–#96, mai 2026)

Découpage reconcilié avec le code courant lors de la création des issues de story :

- **`bank_link_id` reporté à E12** (P05.1.1) : c'est une FK vers une table créée seulement en E12 ; l'ajouter en E05 ferait échouer la migration 0007. E12 l'ajoutera là où la table cible existe.
- **Decimal exact** (P05.2.1) : `default_share_ratio` est `Numeric(5,4)` → la somme se valide en `Decimal` exact (`== Decimal("1.0000")`), pas en float + tolérance 1e-6.
- **FK on-delete** (P05.1.x) : `owner_id` et `account_members.user_id` en `ON DELETE RESTRICT` (état opérationnel, pattern `invitations.invited_by`) ; `account_members → accounts` en `CASCADE`.
- **PATCH = `name` seul** (P05.3.3) : `currency` et `type` sont gelés à la création (la formulation initiale « nom, type uniquement » était contradictoire).
- **S05.4 re-découpée 2 → 3 phases** : `shared/events.py` n'existe pas — introduit comme primitive transverse minimale (P05.4.1) avant son usage. Les `account_member_*` sont des **DomainEvents** (tout membre les déclenche), pas des `admin_audit_logs`.
