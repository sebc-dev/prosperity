# E04 — RBAC + invitations

> **Durée estimée** : 4-6 jours
> **Statut** : not started
> **Dépend de** : E03
> **Bloque** : E05 (RBAC requis pour comptes), E13 (sync rules utilisent rôles)
> **ADRs activés** : 0010 (flow invitation token-based)

---

## Objectif

Implémenter F03 : rôles `admin`/`member`, RBAC matrice, flow d'invitation token-based (table server-only, hash en DB, durée 7j, pré-attribué email, ré-générable, rôle figé `member`). Audit log admin actions.

Livrable agrégé : un admin peut inviter par email, l'invité reçoit un lien `/accept-invite?token=...`, accepte → devient `member`, l'admin peut promouvoir `member → admin` séparément avec audit.

---

## Stories

### S04.1 — Enum rôles + RBAC primitives

**Livrable observable** : décorateurs `require_admin`, `require_member` utilisables dans tous les modules.

| Phase | Description | Diff |
|---|---|---|
| **P04.1.1** | Enum de rôle dans `modules/auth/domain.py` (`admin`, `member`, réutilise `UserRole`). Validations dans `User.role` + round-trip PG ENUM. Tests | ~60 |
| **P04.1.2** | Depends FastAPI : `require_admin`, `require_member` dans `auth/transports/dependencies.py`, re-exposés via `auth.public`. (Pas `shared/` : le contrat import-linter #3 interdit `shared → modules.*`.) Tests httpx : route protégée admin retourne 403 pour member, 200 pour admin | ~120 |
| **P04.1.3** | `auth.public.promote_to_admin(user_id, by_admin_id)` : transition `member → admin` **atomique** (UPDATE conditionnel) avec log audit. Refuse si user déjà admin et si l'acteur n'est pas un admin actif. Tests | ~120 |

---

### S04.2 — Audit log admin

**Livrable observable** : table `admin_audit_logs` (server-only), `auth.public.log_admin_action(action, by, target, metadata)` opérationnel.

| Phase | Description | Diff |
|---|---|---|
| **P04.2.1** | Modèle `AdminAuditLog` : `id`, `action` (text enum : `invite_sent`, `invite_revoked`, `user_promoted`, `user_disabled`, `2fa_reset_via_db`...), `actor_user_id`, `target_user_id` NULL, `metadata` jsonb, `created_at`. Server-only (pas dans sync rules) | ~80 |
| **P04.2.2** | Migration `0005_admin_audit_logs.py` + service `log_admin_action`. Test : log d'une action, retrouvée par requête. | ~80 |

---

### S04.3 — Table `invitations` + token

**Livrable observable** : on peut créer une invitation, son token raw est retourné une seule fois, hashé en DB.

| Phase | Description | Diff |
|---|---|---|
| **P04.3.1** | Modèle `Invitation` : `id`, `email` (avec partial unique index where `accepted_at IS NULL AND revoked_at IS NULL`), `invited_by` FK, `invited_at`, `expires_at` (= invited_at + 7d), `accepted_at` NULL, `revoked_at` NULL, `token_hash` (sha256). Server-only | ~80 |
| **P04.3.2** | Migration `0006_invitations.py` + index partial unique. Test : tentative de créer 2 invitations pending pour le même email échoue | ~100 |
| **P04.3.3** | Service `invitations.py` : `create(email, by_admin_id) → raw_token`, `regenerate(invitation_id) → new_raw_token` (l'ancien hash est remplacé), `revoke(invitation_id)`. Tests intégration | ~150 |

---

### S04.4 — Routes invitation (admin)

**Livrable observable** : `POST /invitations`, `GET /invitations` (liste pending), `POST /invitations/{id}/regenerate`, `DELETE /invitations/{id}` (révoque) — tous admin-only.

| Phase | Description | Diff |
|---|---|---|
| **P04.4.1** | Routes `POST /invitations` + `GET /invitations`. Tests httpx (admin OK, member 403). Audit log inscrit à chaque action | ~150 |
| **P04.4.2** | Routes `POST /invitations/{id}/regenerate` + `DELETE /invitations/{id}`. Tests httpx | ~120 |
| **P04.4.3** | Hook email : à la création/régénération, envoyer l'email via `notifications` ? **Non** — `notifications` n'existe pas encore (V1). En MVP : log warning "invitation envoyée à X, token : Y" dans la console, l'admin doit transmettre manuellement le lien. TODO documenté pour V1 | ~50 |

---

### S04.5 — Flow `/accept-invite`

**Livrable observable** : `GET /accept-invite?token=...` retourne form si token valide, 410 sinon. `POST /accept-invite` crée le user (rôle `member`).

| Phase | Description | Diff |
|---|---|---|
| **P04.5.1** | Route `GET /accept-invite?token=...` : vérifie token hashé existe + non expiré + non accepté + non révoqué. Si OK, retourne email pré-rempli + champ `display_name` + `password`. Sinon 410 Gone | ~100 |
| **P04.5.2** | Route `POST /accept-invite` : valide token (idem), crée user `member`, marque `accepted_at`. Transaction DB unique. Audit log `user_promoted` non — c'est juste une acceptation, pas une promotion. Add action `invite_accepted` à l'enum | ~150 |
| **P04.5.3** | Tests : token expiré, token révoqué, token déjà accepté, token inconnu — tous retournent 410. Token valide → user créé avec rôle `member`. Vérifier que `user.id` est bien généré côté serveur (pas accepté depuis le client) | ~100 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S04.1 (3 phases) | RBAC enum + Depends | 300 | 300 |
| S04.2 (2 phases) | Audit log | 160 | 460 |
| S04.3 (3 phases) | Invitations table | 330 | 790 |
| S04.4 (3 phases) | Routes admin | 320 | 1110 |
| S04.5 (3 phases) | /accept-invite | 350 | 1460 |
| **Total** | **5 stories / 14 phases** | **~1460 lignes** | |

---

## Critères d'acceptation

- [ ] `require_admin`/`require_member` Depends fonctionnent et renvoient 403 sur mauvais rôle (`require_member` fail-closed sur rôle inattendu)
- [ ] Création d'une invitation génère un token aléatoire, hashé en DB
- [ ] Régénérer une invitation invalide l'ancien token
- [ ] Révoquer une invitation rend le lien inutilisable
- [ ] `/accept-invite` avec token valide crée un user `member`, JAMAIS `admin`
- [ ] Promotion `member → admin` est une action séparée (`auth.public.promote_to_admin`), atomique et refusée si l'acteur n'est pas un admin actif (audit non-forgeable)
- [ ] Tous les acts admin sont dans `admin_audit_logs` (server-only)
- [ ] Coverage `modules/auth/service/invitations.py` ≥ 80%

---

## Notes pour l'implémenteur

- Le rôle `member` n'est PAS hardcoded dans `/accept-invite` : c'est la `Invitation.role_to_grant` éventuelle (mais on n'en a pas en V1 — toujours `member`). Si plus tard on veut un type d'invitation "lecteur seul ado", on ajoute `role_to_grant text DEFAULT 'member'`.
- L'email d'invitation est envoyé en clair dans la console en V1 (TODO V1 = intégrer `notifications` quand il existera). Acceptable car self-hosted et l'admin a accès aux logs.
- Le `partial unique index WHERE accepted_at IS NULL AND revoked_at IS NULL` est PostgreSQL-spécifique. Documenté dans le commentaire de migration.
