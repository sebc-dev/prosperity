# Runbook — Transmettre une invitation (MVP self-hosted, S04.4)

> Story : [S04.4 — Routes invitation (admin)](https://github.com/sebc-dev/prosperity/issues/77)
> Lié à : E04 (`docs/roadmap/E04-rbac-invitations.md`), ADR 0010 (flow invitation token-based), OWASP ASVS V8.3.4.

## Pourquoi ce runbook existe

Le module `notifications` (envoi d'email) **n'existe pas encore** en V1. Les
routes `POST /invitations` et `POST /invitations/{id}/regenerate` produisent
un **raw token à usage unique** qui n'est rendu **qu'une seule fois** :

- dans le **corps de la réponse HTTP** (champs `token` et `accept_url`),
  marquée `Cache-Control: no-store` / `Pragma: no-cache` ;
- en **fallback**, dans un log `warning "invitation_link_issued"` côté backend
  (champs `email` + `accept_url`).

Tant qu'aucun canal d'envoi automatique n'existe, **l'admin doit transmettre
le lien manuellement** à l'invité (hors-bande : messagerie chiffrée, en main
propre, etc.).

## ⚠️ Risque assumé : token en clair dans les logs

Le log `invitation_link_issued` contient l'`accept_url`, donc **le raw token
en clair**. C'est une **exception explicite et délibérée** à la règle générale
« ne jamais logger de secret » (et au blacklist de `log_admin_action`) :

- **Scope strict** : self-hosted V1 uniquement.
- **Surface** : les logs backend. Y accéder suppose un accès machine — même
  niveau de confiance que le reset 2FA par SQL manuel (ADR 0013).
- **Atténuation** : le token est **à usage unique** et **expire en 7 jours**.
  Un token déjà accepté ou expiré n'a plus de valeur. En cas de doute sur la
  fuite d'un lien, utiliser `regenerate` (invalide l'ancien) ou `DELETE`
  (révoque).

Ce log **doit être retiré** dès que `notifications` existe (cf.
`# TODO(notifications)` dans `backend/modules/auth/transports/http.py`).

## Procédure — créer et transmettre une invitation

### 1. Créer l'invitation (admin authentifié)

```bash
curl -sS -X POST https://<host>/invitations \
  -H "Authorization: Bearer <access_token_admin>" \
  -H "Content-Type: application/json" \
  -d '{"email": "invite@example.com"}'
```

Réponse `201` (à usage unique — non rejouable) :

```json
{
  "id": "…",
  "email": "invite@example.com",
  "expires_at": "…",
  "token": "<raw_token>",
  "accept_url": "https://<host>/accept-invite?token=<raw_token>"
}
```

> `APP_BASE_URL` doit être positionné en prod pour que `accept_url` pointe sur
> le bon hôte (défaut dev : `http://localhost:8000`).

### 2. Récupérer le lien depuis les logs (canal de secours)

Si le corps de la réponse a été perdu (client qui ne l'affiche pas, etc.),
relire les logs backend après chaque `POST` / `regenerate` :

```
WARNING  invitation_link_issued  email=invite@example.com accept_url=https://<host>/accept-invite?token=…
```

### 3. Transmettre `accept_url` à l'invité

Hors-bande, par un canal de confiance. **Ne pas** le poster dans un canal
partagé/persistant non maîtrisé.

## Gérer le cycle de vie

- **Lien perdu / compromis** : `POST /invitations/{id}/regenerate` → nouveau
  token (l'ancien lien renvoie une erreur côté `/accept-invite` en S04.5).
- **Annuler une invitation** : `DELETE /invitations/{id}` → `204`. L'invitation
  reste en base (audit) mais devient inutilisable. Idempotent.
- **Lister les invitations en attente** : `GET /invitations` (jamais le
  `token_hash`).

Toutes ces actions sont tracées dans `admin_audit_logs`
(`invite_sent` / `invite_regenerated` / `invite_revoked`).
