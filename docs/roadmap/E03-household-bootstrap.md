# E03 — Household singleton + bootstrap `/setup`

> **Durée estimée** : 2-3 jours
> **Statut** : not started
> **Dépend de** : E02
> **Bloque** : E04, E05
> **ADRs activés** : 0008 (`household.base_currency` posé), 0010 (singleton + flow `/setup`)

---

## Objectif

Matérialiser le foyer comme singleton DB et permettre la création du premier admin via flow web `/setup` lock-after-init. Fallback env vars pour scénarios de restore automatisés.

Livrable agrégé : déploiement frais → `GET /setup` retourne le formulaire ; `POST /setup` crée le premier admin + l'unique row `household` ; toute requête `/setup` ultérieure retourne 404.

---

## Stories

### S03.1 — Table `household` singleton

**Livrable observable** : table `household` créée, contrainte CHECK empêche d'insérer un second foyer.

| Phase | Description | Diff |
|---|---|---|
| **P03.1.1** | Modèle `Household` dans `modules/accounts/models.py` (oui, accounts — le foyer est intrinsèquement lié à la propriété de comptes). Champs : `id` UUID fixe `00000000-0000-0000-0000-000000000001`, `name`, `base_currency` (Literal['EUR'] V1), `created_at`, `initialized_at` NULL. Contrainte CHECK SQL `id = singleton UUID` | ~80 |
| **P03.1.2** | Migration `0004_household_singleton.py`. Test niveau 1 schema check. Test intégration : insérer un second household échoue avec contrainte violée | ~100 |
| **P03.1.3** | `accounts.public.get_household()` retourne le singleton ou raise `HouseholdNotInitializedError` si `initialized_at` NULL. Cache process-local (le foyer ne change quasiment jamais) | ~70 |

---

### S03.2 — Flow `/setup` lock-after-init

**Livrable observable** : `GET /setup` répond 200 + form si DB vide, 404 sinon. `POST /setup` crée premier admin + initialise household.

| Phase | Description | Diff |
|---|---|---|
| **P03.2.1** | Route `GET /setup` dans `modules/auth/transports/http.py` : retourne 404 si `users` non vide OU `household.initialized_at` non-null, sinon 200 + schema input attendu. Tests httpx | ~100 |
| **P03.2.2** | Route `POST /setup` : validation email + mdp Pydantic, crée user role `admin` + initialise household (`initialized_at` set), dans une transaction DB unique. Tests httpx (cas vide → succès, cas déjà init → 404) | ~150 |
| **P03.2.3** | Test idempotence : un second appel `POST /setup` après init retourne 404 (jamais 200). Test concurrence : deux `POST /setup` simultanés → un seul réussit (contrainte UNIQUE sur email + CHECK singleton sur household) | ~80 |

---

### S03.3 — Fallback env vars `INITIAL_ADMIN_*`

**Livrable observable** : si `INITIAL_ADMIN_EMAIL` + `INITIAL_ADMIN_PASSWORD_HASH` sont set au démarrage et que `users` est vide, le premier admin est créé automatiquement au boot.

| Phase | Description | Diff |
|---|---|---|
| **P03.3.1** | Dans `backend/main.py`, hook `startup` qui vérifie `users` vide ET env vars présentes ET `household.initialized_at` NULL → crée user admin + init household. Pas d'erreur si env vars absentes (mode normal). Pas de double-init si déjà fait. Tests intégration (avec et sans env vars) | ~130 |
| **P03.3.2** | Documentation runbook `runbooks/initial_admin_via_env.md` : usage, sécurité (`INITIAL_ADMIN_PASSWORD_HASH` doit être un hash Argon2id pré-calculé, pas un mdp en clair) | ~50 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S03.1 (3 phases) | Household singleton | 250 | 250 |
| S03.2 (3 phases) | /setup flow | 330 | 580 |
| S03.3 (2 phases) | Env vars fallback | 180 | 760 |
| **Total** | **3 stories / 8 phases** | **~760 lignes** | |

---

## Critères d'acceptation

- [ ] Table `household` ne peut contenir qu'une seule row (testé via insertion qui échoue)
- [ ] `GET /setup` retourne form si DB vide, 404 sinon
- [ ] `POST /setup` crée admin + init household dans une transaction atomique
- [ ] Re-appel `/setup` après init = 404 systématique
- [ ] Boot avec `INITIAL_ADMIN_EMAIL` + `INITIAL_ADMIN_PASSWORD_HASH` crée l'admin si DB vide
- [ ] Aucun chemin ne permet de créer un user sans soit `/setup` soit (E04) `/accept-invite`
- [ ] CONTEXT.md "Foyer" et "Bootstrap initial" alignés (déjà fait, mais vérifier que rien n'a divergé)

---

## Notes pour l'implémenteur

- L'UUID singleton `00000000-0000-0000-0000-000000000001` est en dur partout (constant Python `HOUSEHOLD_ID` dans `accounts/public.py`). Pas de lookup en DB pour le récupérer.
- Le hash Argon2id de l'env var doit être calculé hors ligne (script `scripts/hash_password.py` à créer dans P03.3.2). Ne JAMAIS mettre un mdp en clair en env var.
- Le hook startup doit être tolérant aux erreurs réseau DB transitoires (retry léger). En cas d'échec, log warning mais ne bloque pas le démarrage de l'app (l'admin pourra `/setup` manuellement).
