# 2FA TOTP : step-up sur création PAT, opt-in par PAT pour `confirm_pending_action`, pas de reset admin-via-app

F01 décrit 2FA TOTP comme V1 optionnel sans préciser ses interactions avec PAT et `confirm_pending_action` (F14), ni le flow de reset. Trois décisions structurantes :

**Step-up obligatoire à la création d'un PAT.** Acte sensible (le PAT persiste, hérite des droits) — on re-demande systématiquement un code TOTP avant la création, même en session déjà 2FA-authentifiée. Pour les utilisateurs sans 2FA, on re-valide le mot de passe à la place (minimum cohérent avec "2FA optionnel"). Protège contre le scénario navigateur emprunté quelques minutes.

**Pas de 2FA par défaut sur `confirm_pending_action`** : ajouter 2FA systématique casserait l'UX du workflow F14 (push → ouvrir app → écran de confirmation → 2FA) au point qu'on ne s'en sert plus. Mais opt-in **par PAT** via `require_2fa_on_confirm: bool` à la création — permet au user paranoïaque de durcir certains PAT (ex. un n8n distant en `read_write`) sans pénaliser les autres.

**Pas de reset admin-via-app.** L'admin ne voit aucune donnée user (F03) ; lui donner le pouvoir de désactiver le 2FA d'un autre user serait un vecteur de takeover silencieux. Le reset cascade : self-service via recovery code → si tous perdus, **accès physique machine** (SQL manuel `UPDATE users SET totp_secret = NULL ...` documenté dans `runbooks/2fa_reset.md`). Pour un foyer (admin = conjoint, coloc dans la même maison), c'est pratique.

## Consequences

- Tables : `users.totp_secret` (encrypted at rest via pgcrypto), `totp_enrolled_at`, `totp_recovery_codes_hash[]`, `totp_recovery_codes_used_at[]`. Table `auth_challenges` server-only short-lived pour les `challenge_id` de login en cours.
- Le runbook `runbooks/2fa_reset.md` doit être en place avant la mise en prod de la 2FA — sinon le premier utilisateur qui perd ses recovery codes est bloqué.
- Tests : enrollment full flow, recovery code consumption, expired challenge, step-up sur création PAT, opt-in 2FA sur `confirm_pending_action`.
- Audit log : enrollment, désactivation 2FA, recovery code utilisé, reset manuel via DB (audit log laissé par le script de reset documenté).
