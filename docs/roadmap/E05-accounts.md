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
| **P05.1.1** | Modèle `Account` dans `modules/accounts/models.py` : `id`, `household_id` FK (toujours singleton), `name`, `type` (Literal['courant','livret','epargne','especes','credit']), `currency` ISO 4217, `owner_id` FK NULL (personnel), `created_at`, `archived_at` NULL, `bank_link_id` FK NULL (préparation E12). Pas de constraint "owner XOR members" en SQL — vérifié au service | ~120 |
| **P05.1.2** | Modèle `AccountMember` : `id`, `account_id` FK, `user_id` FK, `default_share_ratio` (Decimal 5,4, sum = 1.0 par account vérifié au service), `joined_at`. Unique index `(account_id, user_id)` | ~80 |
| **P05.1.3** | Migration `0007_accounts.py`. Test niveau 1 schema check. Test : on ne peut pas supprimer un user qui a des owner_id sans CASCADE/SET NULL — décision : on garde le user disabled (audit), on ne supprime pas | ~100 |

---

### S05.2 — Validation devise + invariant propriété

**Livrable observable** : `accounts.service.validate_creation()` rejette devise ≠ household, rejette compte sans owner ET sans members, rejette quote-parts ne sommant pas à 1.

| Phase | Description | Diff |
|---|---|---|
| **P05.2.1** | `accounts/domain.py` : `AccountValidator` pur — règles `currency == household.base_currency`, `(owner_id IS NOT NULL) XOR (len(members) ≥ 2)`, `sum(member.default_share_ratio) == 1.0` (tolérance 1e-6 pour floats convertis depuis Decimal). Tests example + Hypothesis | ~150 |
| **P05.2.2** | `accounts.service` : `create_personal(owner_id, ...)`, `create_shared(members_with_ratios, ...)`. Chaque crée Account + AccountMember(s) en transaction DB unique. Tests intégration | ~180 |

---

### S05.3 — Routes accounts (RBAC)

**Livrable observable** : `POST /accounts`, `GET /accounts` (filtré au user), `GET /accounts/{id}`, `PATCH /accounts/{id}` (membres uniquement), `DELETE /accounts/{id}` → archivage.

| Phase | Description | Diff |
|---|---|---|
| **P05.3.1** | Schemas Pydantic `AccountCreatePersonal`, `AccountCreateShared`, `AccountResponse`, `AccountMemberInput`. Route `POST /accounts` (deux endpoints distincts `/accounts/personal` et `/accounts/shared` pour éviter polymorphisme Pydantic complexe). Tests httpx | ~180 |
| **P05.3.2** | Route `GET /accounts` qui filtre selon le user authentifié : ses comptes personnels + comptes communs où il est membre. **L'admin n'est PAS exempté** (cf. F03 invariant). Tests : admin ne voit jamais les comptes personnels des autres | ~150 |
| **P05.3.3** | Routes `GET /accounts/{id}` (404 si pas accès même pour admin) + `PATCH` (nom, type uniquement — `currency` et `type` initiaux non éditables) + `DELETE` (archivage, pas suppression dure). Tests | ~200 |

---

### S05.4 — `account_members` management

**Livrable observable** : un membre peut être ajouté/retiré d'un compte commun par un autre membre, audit log laissé.

| Phase | Description | Diff |
|---|---|---|
| **P05.4.1** | Routes `POST /accounts/{id}/members` + `DELETE /accounts/{id}/members/{user_id}` + `PATCH /accounts/{id}/members/{user_id}` (édition `default_share_ratio`). Vérification : tout membre actuel peut éditer (pas seulement admin). Pas retirer le dernier membre (laisserait compte orphelin). Tests | ~200 |
| **P05.4.2** | Audit log : `account_member_added`, `account_member_removed`, `share_ratio_updated`. Émis via `shared/events.py` (préparation E08 budgets qui souscriront aux changements de quote-parts). Tests | ~100 |

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
| S05.1 (3 phases) | Modèles | 300 | 300 |
| S05.2 (2 phases) | Validation domain | 330 | 630 |
| S05.3 (3 phases) | Routes | 530 | 1160 |
| S05.4 (2 phases) | Members management | 300 | 1460 |
| S05.5 (2 phases) | Hypothesis | 230 | 1690 |
| **Total** | **5 stories / 12 phases** | **~1690 lignes** | |

---

## Critères d'acceptation

- [ ] Compte personnel ne peut pas être créé sans owner
- [ ] Compte commun ne peut pas être créé sans ≥ 2 members + sum(ratios) == 1
- [ ] Création d'un compte avec devise ≠ household.base_currency échoue (validation)
- [ ] Admin ne voit pas les comptes personnels des autres users via `GET /accounts` (F03)
- [ ] Suppression d'un compte = archivage (`archived_at` set), pas suppression dure
- [ ] Modification de `default_share_ratio` re-balance ou échoue, jamais ne casse sum=1
- [ ] DomainEvent `account_member_*` publiés via `shared/events.py`
- [ ] Coverage `modules/accounts/domain.py` ≥ 90%, service ≥ 75%

---

## Notes pour l'implémenteur

- Les `default_share_ratio` sont stockés en `Decimal(5,4)` (max 0.9999, précision 4 décimales — suffit pour 50/25/25 etc., et évite les float-rounding pénibles).
- Les routes `POST /accounts/personal` et `POST /accounts/shared` sont **distinctes** pour éviter le polymorphisme Pydantic (qui est faisable mais alourdit la doc OpenAPI). Côté UI on choisit le type d'abord, puis le formulaire.
- Quand un user est `disabled` (E04 promotion ou autre flow), ses comptes personnels restent en DB mais deviennent inaccessibles par `GET /accounts`. Pas de transfert auto à un autre user — décision F02 (option : ajouter un flow admin de transfert en V1).
- L'invariant `sum(default_share_ratio) == 1` est vérifié au service, pas en CHECK SQL (CHECK SQL multi-row PostgreSQL = trigger, trop complexe pour ce besoin).
