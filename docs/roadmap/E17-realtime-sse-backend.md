# E17 — Realtime backend (SSE : token + stream + resume)

> **Durée estimée** : 3-4 jours
> **Statut** : not started
> **Dépend de** : E02 (auth/JWT), E04 (notifications scaffolding via mini-bus)
> **Bloque** : E14 (S14.7 — wrapper SSE client, #211)
> **ADRs activés** : 0012 (SSE auth token court-lived + heartbeat 30s + resume `Last-Event-ID`), 0016 (JWT aud/iss), cohérence 0003 (`pending_actions` server-only)

---

## Objectif

Exposer le canal **push serveur → client** par Server-Sent Events (ADR 0012), aujourd'hui **absent** côté backend — gap découvert à la création des stories E14 (#205-#211), bloquant #211 / S14.7 (le wrapper SSE client).

Distinct d'E13 (PowerSync = sync de **données** download/upload) : la SSE pousse des **notifications / signaux** (ADR 0003 §`pending_actions` server-only « lecture via API + SSE »).

Livrable agrégé : un client authentifié appelle `POST /sse/token`, ouvre `GET /sse/stream?token=…`, reçoit un heartbeat 30 s, et après une coupure réémet `Last-Event-ID` pour rejouer les events manqués (buffer 5 min / 100 events par user).

---

## Stories

### S17.1 — SSE backend (token + stream + broadcaster + resume)

| Phase | Description | Diff |
|---|---|---|
| **P17.1.1** | Scaffolding `modules/sse/` (`public`/`service`/`transports`) + placement dans le graphe directionnel (ADR 0005) + contrat import-linter `2-sse` (gabarit `2-sync`). Tests d'archi : `lint-imports` vert, surface publique | ~120 |
| **P17.1.2** | Token SSE scopé : `issue_sse_token` / `verify_sse_token` (audience dédiée `prosperity-sse`, TTL 5 min, ADR 0016) + `POST /sse/token` (auth JWT normal → token scopé). Tests : token valide 5 min, mauvaise audience rejetée, JWT requis | ~150 |
| **P17.1.3** | Broadcaster in-memory : registre de connexions par user (multi-onglets), ring buffer 5 min / 100 events par user, `publish(user_id, event)` + `subscribe(user_id)`. Tests unitaires (broadcast, éviction 5 min, dépassement 100) | ~200 |
| **P17.1.4** | `GET /sse/stream?token=…` : `text/event-stream`, auth via query token, heartbeat 30 s, replay post-`Last-Event-ID` puis stream live. Tests intégration (httpx streaming) : connexion, heartbeat, reconnect + `Last-Event-ID`, buffer dépassé, token expiré | ~250 |
| **P17.1.5** | Câblage events → broadcaster en livraison **post-commit** (le mini-bus dispatche in-transaction, S13.6 ; la diffusion SSE sort post-commit via `BackgroundTasks`) + runbook `runbooks/sse.md` (redaction `?token=` logs Caddy/Cloudflare, idle timeouts). `notifications` étant un stub → câblage minimal/extensible. Tests | ~180 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S17.1 (5 phases) | SSE backend (token + stream + buffer/resume) | 900 | 900 |
| **Total** | **1 story / 5 phases** | **~900 lignes** | |

---

## Critères d'acceptation

- [ ] `POST /sse/token` (auth JWT normal) → token scopé `sse_subscribe`, TTL **5 min** ; sans JWT → 401
- [ ] `GET /sse/stream?token=…` → `text/event-stream` ; 401 si token absent / invalide / mauvaise audience / expiré
- [ ] **Heartbeat 30 s** (sous l'idle timeout 100 s Cloudflare)
- [ ] `Last-Event-ID` → replay des events post-id depuis le buffer (5 min / 100 par user) ; au-delà → re-sync REST documenté
- [ ] **Multi-onglets** : N connexions par user, broadcast à chacune
- [ ] Livraison **post-commit** : un event n'est diffusé qu'après commit de sa transaction
- [ ] Token `?token=` redacté dans les logs reverse proxy (runbook `runbooks/sse.md`)
- [ ] `lint-imports` vert (nouveau contrat `2-sse`)

---

## Notes pour l'implémenteur

- **Numérotation hors-séquence assumée** : E17 a été créé *après* E14 (gap SSE découvert à la création des stories E14). Topologiquement, **E17 précède E14 S14.7** (qui en dépend) — le numéro ne reflète pas l'ordre d'exécution. À faire avant l'intégration end-to-end de S14.7.
- **Nouveau module `modules/sse/`** → place au **sommet** du graphe directionnel (ADR 0005, au-dessus de `notifications` qu'il consomme) + contrat `2-sse` (mirror `2-sync`) + *consumer-only* (contrats 5/6). `test_importlinter_coverage` doit voir `sse`.
- **Token scopé (ADR 0016)** : audience distincte (`prosperity-sse`) + TTL 5 min ; `verify_sse_token` impose `audience=`/`issuer=`. Le query param est loggable → fenêtre limitée à 5 min + redaction proxy.
- **Livraison POST-COMMIT** : le mini-bus dispatche **in-transaction** (S13.6) ; la diffusion SSE sort **post-commit** (hook `BackgroundTasks`, même chemin que le delivery email/push différé). Ne jamais diffuser depuis l'intérieur de la transaction.
- **Buffer in-memory** (pas de migration) ; la table durable `pending_actions` (ADR 0003, inexistante) est un **concern séparé** à planifier avec le module notifications réel.
- **`notifications` est un stub** : câblage minimal en P17.1.5, extensible.
