# E02 — Auth foundations

> **Durée estimée** : 3-5 jours
> **Statut** : not started
> **Dépend de** : E01
> **Bloque** : E03, E04, E05
> **ADRs activés** : aucun (E02 reste sous la couche PAT/2FA — ADR 0013 viendra en V1)

---

## Objectif

Implémenter F01 dans sa version MVP : email + Argon2id (`pwdlib`) + JWT access (15 min) + refresh token (30 j, stocké en DB, révocable), `users` server-only. **Pas de PAT, pas de 2FA en MVP** (V1 features, hors scope ici).

Livrable agrégé : un utilisateur peut faire `POST /auth/login`, recevoir un access + refresh, faire `POST /auth/refresh` pour renouveler, et `POST /auth/logout` pour révoquer son refresh.

---

## Stories

### S02.1 — Modèle `User` + hash mot de passe

**Livrable observable** : table `users` créée, factory `UserFactory` produit un user avec mdp hashé.

| Phase | Description | Diff |
|---|---|---|
| **P02.1.1** | Add deps `pwdlib[argon2]` + `sqlalchemy[asyncio]`. Modèle `User` dans `modules/auth/models.py` : `id` UUID, `email` unique, `password_hash`, `display_name`, `role` (Literal['admin','member']), `created_at`, `disabled_at` NULL. Public surface vide pour l'instant | ~100 |
| **P02.1.2** | Migration Alembic `0002_users.py`. Test niveau 1 schema check. | ~80 |
| **P02.1.3** | `tests/factories/sqlalchemy.py` : `UserFactory` async-compatible. Test intégration : crée un user via factory, retrouve via SQLA, mdp vérifié via pwdlib | ~120 |

---

### S02.2 — JWT issuance et verification

**Livrable observable** : `auth.public.issue_access_token(user_id)` retourne un JWT valide, `auth.public.verify_access_token(token)` retourne le `user_id` ou lève `InvalidTokenError`.

| Phase | Description | Diff |
|---|---|---|
| **P02.2.1** | Add dep `python-jose[cryptography]`. Helpers `issue_access_token` / `verify_access_token` dans `modules/auth/service/jwt.py`. Secret en `pydantic-settings`. Tests unitaires : issue + verify round-trip, expiration 15 min vérifiée, signature corrompue rejetée | ~150 |
| **P02.2.2** | Exposer dans `modules/auth/public.py` : `issue_access_token`, `verify_access_token`, `InvalidTokenError`, `ExpiredTokenError`. Test import-linter passe (les autres modules peuvent importer ce qui est exposé, rien d'autre) | ~40 |

---

### S02.3 — Refresh tokens (DB-stored, révocables)

**Livrable observable** : table `refresh_tokens`, on peut issuer/vérifier/révoquer un refresh token.

| Phase | Description | Diff |
|---|---|---|
| **P02.3.1** | Modèle `RefreshToken` : `id`, `user_id` FK, `token_hash` (sha256), `issued_at`, `expires_at` (30j), `revoked_at` NULL, `device_label` optionnel. Migration `0003_refresh_tokens.py` | ~120 |
| **P02.3.2** | Service `refresh_tokens.py` : `issue(user_id, device_label) → raw_token`, `verify(raw_token) → user_id ou raise`, `revoke(token_hash)`. Tests intégration | ~150 |
| **P02.3.3** | Tests : un refresh token expiré ne valide pas, un refresh token révoqué ne valide pas, on peut révoquer un refresh sans toucher aux autres | ~80 |

---

### S02.4 — Routes auth + middleware FastAPI

**Livrable observable** : `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` opérationnels, middleware `get_current_user` utilisable comme `Depends`.

| Phase | Description | Diff |
|---|---|---|
| **P02.4.1** | `modules/auth/transports/http.py` : route `POST /auth/login` (email + password → access + refresh). Schemas Pydantic input/output dans `modules/auth/schemas.py`. Tests httpx avec `db_session` | ~180 |
| **P02.4.2** | Routes `POST /auth/refresh` et `POST /auth/logout`. Tests httpx | ~120 |
| **P02.4.3** | `modules/auth/public.py` : `get_current_user` (Depends FastAPI qui extrait l'access JWT, vérifie, retourne `User` ou 401). Tests : route protégée renvoie 401 sans token, 401 avec token expiré, 200 avec token valide | ~120 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S02.1 (3 phases) | User + hash | 300 | 300 |
| S02.2 (2 phases) | JWT | 190 | 490 |
| S02.3 (3 phases) | Refresh tokens | 350 | 840 |
| S02.4 (3 phases) | Routes + middleware | 420 | 1260 |
| **Total** | **4 stories / 11 phases** | **~1260 lignes** | |

---

## Critères d'acceptation

- [ ] `POST /auth/login` (email + mdp) retourne access + refresh JWTs
- [ ] Access JWT verify accepte un token valide, rejette un expiré et un corrompu
- [ ] `POST /auth/refresh` renouvelle l'access
- [ ] `POST /auth/logout` révoque le refresh, le réutiliser ensuite échoue
- [ ] `get_current_user` Depends utilisable depuis n'importe quel autre module
- [ ] Import-linter passe : seul `auth.public` est importable cross-module
- [ ] Coverage `modules/auth/service/` ≥ 70%

---

## Notes pour l'implémenteur

- Le `password_hash` est lazy à la création (`UserFactory` doit accepter un mdp en clair et hasher). Évite les fixtures avec hashes pré-calculés qui prennent un temps fou à recalculer.
- Refresh token : on stocke le `sha256` du token, jamais le token en clair. Comportement identique au PAT (E10/V1) — penser à factoriser plus tard quand PAT arrivera.
- Le rôle `role` est sur `User` directement pour l'instant. Si on veut promouvoir membre → admin (E04), c'est juste un UPDATE de cette colonne avec audit log.
- Pas de `/auth/register` public : la création de user passe **uniquement** par `/setup` (E03) ou `/accept-invite` (E04).
