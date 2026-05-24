# E16 — Deployment (Podman Quadlet + Caddy + Cloudflare Tunnel + Tailscale + Restic→B2)

> **Durée estimée** : 5-7 jours
> **Statut** : not started
> **Dépend de** : E15
> **Bloque** : production
> **ADRs activés** : aucun (matérialise les choix de stack architecture §1)

---

## Objectif

Déployer le MVP en self-hosted : Postgres + backend + PowerSync Service + frontend statique + Caddy reverse proxy + Cloudflare Tunnel pour exposition + Tailscale pour accès admin + Restic→B2 pour backups. Runbooks pour les opérations critiques (release, restore, 2FA reset, SCA renewal anticipé).

Livrable agrégé : un déploiement frais en environ 1h sur une machine Linux (VPS ou home server) suit le runbook. L'app est accessible via HTTPS (Cloudflare Tunnel), les backups tournent nightly, l'admin a un accès SSH via Tailscale uniquement.

---

## Stories

### S16.1 — Containerfiles (backend + frontend)

| Phase | Description | Diff |
|---|---|---|
| **P16.1.1** | `backend/Containerfile` : multi-stage build (build deps → runtime), Python 3.13 slim, uv install, exposer port 8000, healthcheck `/healthz`. Tests : `podman build` puis `podman run` réussit, `/healthz` répond | ~120 |
| **P16.1.2** | `client/Containerfile` : multi-stage (Node 22 build Vite → nginx-alpine serve static). Build output `/usr/share/nginx/html`. Tests : container démarre, sert l'app | ~100 |
| **P16.1.3** | `.github/workflows/release.yml` : sur tag git `v*`, build et push images vers ghcr.io (backend + frontend). Tests : tag manuel → images publiées | ~120 |

---

### S16.2 — Quadlet units

| Phase | Description | Diff |
|---|---|---|
| **P16.2.1** | `deploy/quadlet/postgres.container` : Postgres 17 alpine, volume persistant, env vars (POSTGRES_PASSWORD via fichier secrets), logical replication activée pour PowerSync | ~120 |
| **P16.2.2** | `deploy/quadlet/backend.container` : image ghcr.io/.../backend, env vars (DB DSN, JWT secret, etc. via fichier secrets), depends postgres, expose port interne uniquement | ~100 |
| **P16.2.3** | `deploy/quadlet/powersync.container` : PowerSync Service Open Edition, config monté en volume, depends postgres | ~100 |
| **P16.2.4** | `deploy/quadlet/frontend.container` + `deploy/quadlet/caddy.container` : Caddy reverse proxy en front, frontend nginx en back. Caddyfile dans volume | ~150 |
| **P16.2.5** | `deploy/quadlet/*.network` : un network podman partagé entre tous les services. Tests : `systemctl start prosperity.target` démarre tout, tout est up | ~80 |

---

### S16.3 — Caddy config

| Phase | Description | Diff |
|---|---|---|
| **P16.3.1** | `deploy/caddy/Caddyfile` : reverse proxy `/api/* → backend:8000`, `/sync/* → powersync:8080`, `/sse/* → backend:8000` (preserve SSE headers + redact `?token=` dans les logs cf. ADR 0012), root `/` → frontend:80. TLS désactivé (Cloudflare Tunnel gère). Tests : config valide | ~100 |
| **P16.3.2** | Logs Caddy en JSON structuré dans `/var/log/caddy/access.log` avec rotation. Redaction des query params sensibles. Tests | ~80 |

---

### S16.4 — Cloudflare Tunnel + Access

| Phase | Description | Diff |
|---|---|---|
| **P16.4.1** | `deploy/cloudflared/config.yaml` + `cloudflared.container` Quadlet unit. Tunnel ID + ingress vers Caddy. Runbook : créer le tunnel via `cloudflared tunnel create` (manuel), copier le token dans secrets | ~120 |
| **P16.4.2** | Optionnel V1.5 : Cloudflare Access (Zero Trust) devant le MCP HTTP endpoint (cf. F14 / CONTEXT.md PAT compléments structurels). MVP : pas Access, juste le Tunnel. Documenté pour V1+ | ~80 |
| **P16.4.3** | Runbook `runbooks/cloudflare_setup.md` : étapes manuelles dans le dashboard Cloudflare, ce qui est dans Terraform, ce qui ne l'est pas (en MVP : tout manuel — Terraform plus tard si justifié) | ~100 |

---

### S16.5 — Tailscale

| Phase | Description | Diff |
|---|---|---|
| **P16.5.1** | `deploy/tailscale/install.sh` : install Tailscale sur l'hôte, `tailscale up` + ACL pour réduire l'accès à mon device. Runbook étape par étape | ~100 |
| **P16.5.2** | SSH config : désactiver l'accès SSH public (port 22 firewall fermé), accessible uniquement via Tailscale (port 22 sur l'IP Tailscale). Tests : ssh fail depuis IP publique, succeed depuis Tailscale | ~80 |

---

### S16.6 — Restic → B2 backup

| Phase | Description | Diff |
|---|---|---|
| **P16.6.1** | Script `deploy/backup/restic-postgres.sh` : `pg_dump` (depuis le container Postgres via `podman exec`), pipe vers `restic backup` cible Backblaze B2. Retention 30 jours quotidien + 4 semaines hebdomadaire + 12 mois mensuel | ~150 |
| **P16.6.2** | `deploy/quadlet/restic-backup.timer` + `.service` : déclenche nightly à 03:00 UTC (1h après le cron recurring rules de 02:00). Tests : trigger manuel, vérifier que le snapshot apparaît côté B2 | ~120 |
| **P16.6.3** | Runbook `runbooks/restore.md` : restore complet depuis B2 → DB locale → app remontée. Procédure testée au moins 1 fois en MVP (chaos drill) | ~150 |

---

### S16.7 — Runbooks production

| Phase | Description | Diff |
|---|---|---|
| **P16.7.1** | `runbooks/release.md` : procédure pour publier une release (tag git → CI → pull images sur le serveur → restart Quadlet). Tests : faire une release MVP-v0.1.0 | ~100 |
| **P16.7.2** | `runbooks/2fa_reset.md` (cf. ADR 0013), `runbooks/recurring_rules_cron.md` (cf. ADR 0007 — heure 02:00 UTC documentée), `runbooks/enable_banking_sca_renewal.md` (préparation V1, déjà décrit dans stratégie de tests §4.7) | ~200 |
| **P16.7.3** | `runbooks/dr.md` (disaster recovery) : machine totalement perdue, restore depuis B2 sur nouvelle machine. Procédure complète, testée 1 fois | ~150 |

---

### S16.8 — Production smoke tests

| Phase | Description | Diff |
|---|---|---|
| **P16.8.1** | `scripts/prod-smoke.sh` : checklist de smoke tests post-déploiement (curl `/healthz`, login admin, créer transaction, vérifier sync, vérifier SSE). Tests : à lancer après chaque release | ~120 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S16.1 (3 phases) | Containerfiles + release CI | 340 | 340 |
| S16.2 (5 phases) | Quadlet units | 550 | 890 |
| S16.3 (2 phases) | Caddy config | 180 | 1070 |
| S16.4 (3 phases) | Cloudflare Tunnel | 300 | 1370 |
| S16.5 (2 phases) | Tailscale | 180 | 1550 |
| S16.6 (3 phases) | Restic backup | 420 | 1970 |
| S16.7 (3 phases) | Runbooks | 450 | 2420 |
| S16.8 (1 phase) | Smoke tests | 120 | 2540 |
| **Total** | **8 stories / 22 phases** | **~2540 lignes** | |

---

## Critères d'acceptation

- [ ] `systemctl start prosperity.target` sur l'hôte démarre tous les services (postgres, backend, powersync, frontend, caddy, cloudflared)
- [ ] L'app est accessible via le hostname Cloudflare configuré (HTTPS)
- [ ] SSH refusé depuis IP publique, accessible via Tailscale
- [ ] Backup nightly Restic→B2 réussit, visible dans la console B2
- [ ] Restore depuis backup testé au moins 1 fois (chaos drill)
- [ ] Runbooks `release`, `restore`, `2fa_reset`, `recurring_rules_cron` présents
- [ ] Smoke tests `scripts/prod-smoke.sh` passent après release
- [ ] Aucun secret en clair dans le repo (tous via fichiers secrets podman ou env vars chiffrés)

---

## Notes pour l'implémenteur

- **Podman Quadlet** est plus simple que docker-compose en prod (systemd-native, pas de daemon dépendant). Mais le tooling tournant peut surprendre. Doc README pas-à-pas.
- Les secrets : utiliser `podman secret` (Quadlet supporte `Secret=` dans les units). Jamais d'env var en clair dans les unit files.
- Cloudflare Tunnel : créer le tunnel via `cloudflared tunnel create prosperity` (manuel), récupérer le token, le mettre en secret. Le tunnel UUID et les ingress sont dans `config.yaml` versionné.
- Tailscale ACL : limiter au strict minimum (juste mon device + ssh + ports 5432 admin éventuel). Pas d'exposition large.
- Restore drill : faire le drill **avant** la mise en prod réelle. C'est la garantie qu'un backup B2 est utilisable, pas une assumption.
- Les SSE via Cloudflare : vérifier que la config Cloudflare Tunnel n'inhibe pas le streaming (par défaut OK avec HTTP/2). Tester explicitement.
- B2 (Backblaze) free tier : 10 GB stockage, 1 GB/jour download. Largement suffisant pour un foyer (~100 MB/snapshot, 30 snapshots = 3 GB).
