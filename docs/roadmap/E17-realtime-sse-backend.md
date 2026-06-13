# E17 — Realtime backend (SSE : token + stream + resume)

> **Durée estimée** : 4-5 jours
> **Statut** : not started
> **Dépend de** : E02 (auth/JWT), E04 (notifications scaffolding via mini-bus)
> **Bloque** : E14 (S14.7 — wrapper SSE client, #211)
> **Lié** : S02.5 (#73 — stack rate-limit, pour `POST /sse/token`)
> **ADRs activés** : 0012 (SSE token court-lived + heartbeat 30s + resume `Last-Event-ID`), 0016 (JWT aud/iss), cohérence 0003 (`pending_actions` server-only), 0005 (contrat import `2-sse`)

> ♻️ **v2 — révisé suite à l'analyse 3-agents (archi/sécu/tests)** : fondement post-commit corrigé (mécanisme inexistant → listener `after_commit`), disponibilité bornée (anti-DoS), décisions techniques tranchées. Détail dans #214.

---

## Objectif

Exposer le canal **push serveur → client** par Server-Sent Events (ADR 0012), absent côté backend — gap découvert à la création des stories E14 (#205-#211), bloquant #211 / S14.7.

Distinct d'E13 (PowerSync = sync de **données**) : la SSE pousse des **signaux** (ADR 0003 §`pending_actions`). **Invariant** : un event SSE ne transporte qu'un **signal/id, jamais de PII** ; le client re-fetch via REST authentifié.

Livrable agrégé : `POST /sse/token` → `GET /sse/stream?token=…` (heartbeat 30 s), reconnexion `Last-Event-ID` → replay **exactly-once** depuis le buffer (5 min / 100 events par user).

---

## Stories

### S17.1 — SSE backend (token + stream + broadcaster + resume)

| Phase | Description | Diff |
|---|---|---|
| **P17.1.1** | Scaffolding `modules/sse/` + frontière d'imports : couche `sync \| savings \| sse` (contrat 1, sommet = `mcp`), nouveau contrat `2-sse` (mirror `2-sync`), `sse` dans contrats 5/6 ; `ignore_imports` = uniquement les 9 second-hops `auth.public → auth.X` (PAS de `notifications`, surface vide). Tests d'archi (`lint-imports`, `test_importlinter_coverage`, `test_sse_public_surface`) | ~250 |
| **P17.1.2** | Token SSE scopé (ADR 0016) : settings `jwt_sse_audience="prosperity-sse"` + `jwt_sse_ttl_seconds=300` (distincts) ; `issue_sse_token`/`verify_sse_token` (imposent `audience`/`issuer`, rejettent l'absence de `aud`) + `POST /sse/token` (auth `get_current_user`). Tests : valide 5 min, **confusion d'audience bidirectionnelle**, sans `aud`, JWT requis | ~180 |
| **P17.1.3** | Broadcaster + ring buffer **pur in-memory** : registre par user, ring 5 min / 100, **plafond connexions/user** (fail-closed), `publish`/`subscribe`/**désinscription**, **horloge injectable**. Tests unitaires DB-free + **property Hypothesis** (buffer pur, exception §4.2) : `replay_after(id)` = sous-séquence ordonnée strictement postérieure capée fenêtre (exactly-once) ; `@example` aux frontières (id=dernier, inconnu/forgé, buffer vide) | ~280 |
| **P17.1.4** | `GET /sse/stream?token=…` : **`StreamingResponse` natif** + désinscription au disconnect (`request.is_disconnected()`), **heartbeat paramétrable**, **fermeture à l'expiration du token** (≤ 5 min, anti slow-loris) ; replay post-`Last-Event-ID` puis live ; hors fenêtre → frame `resync`. Tests intégration httpx streaming (broadcaster injectable) : heartbeat court, reconnect, désinscription, token expiré → fermé, hors-fenêtre → `resync`, multi-onglets, 401 (absent/sig/aud/expiré/user inexistant → pas 500) | ~280 |
| **P17.1.5** | Livraison **POST-COMMIT** : listener SQLAlchemy `after_commit` (gabarit `accounts/service/setup.py:154`) collectant les events SSE produits in-transaction et les flush au broadcaster après commit + producteur minimal/seam de test (`notifications` stub). Runbook `runbooks/sse.md` (redaction `?token=` proxy **et** application, contrainte mono-process, idle timeouts, révocation = TTL). Tests : **rollback → AUCUNE diffusion**, **commit → exactly-once** (broadcaster espionné) | ~250 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S17.1 (5 phases) | SSE backend (token + stream + buffer/resume + post-commit) | 1240 | 1240 |
| **Total** | **1 story / 5 phases** | **~1240 lignes** | |

---

## Critères d'acceptation

- [ ] `POST /sse/token` (auth JWT) → token `prosperity-sse`, TTL **5 min** ; sans JWT → 401
- [ ] **Confusion d'audience fermée des deux côtés** (+ token sans `aud` rejeté)
- [ ] `GET /sse/stream?token=…` → `text/event-stream` ; 401 token absent/invalide/mauvaise audience/expiré ; user inexistant → jamais 500
- [ ] **Heartbeat** (30 s prod, paramétrable) + **fermeture à l'expiration du token** (durée de vie ≤ 5 min)
- [ ] **Plafond de connexions par user** (fail-closed) — anti-DoS/OOM
- [ ] `Last-Event-ID` → replay **exactly-once** ; hors fenêtre → `resync` ; forgé/malformé → re-sync, jamais le buffer d'autrui
- [ ] **Isolation cross-user** (filtre sur le `sub` du token)
- [ ] **Multi-onglets** : N connexions (≤ plafond) par user, broadcast à chacune
- [ ] **Livraison POST-COMMIT prouvée** : committée → diffusée une fois ; rollbackée → **jamais**
- [ ] Token redacté (proxy **et** application) ; contrainte mono-process documentée
- [ ] `lint-imports` vert (contrat `2-sse` + `sse` dans 1/5/6)

---

## Notes pour l'implémenteur

- **Numérotation hors-séquence assumée** : E17 a été créé après E14 (gap découvert) ; il **précède topologiquement** E14 S14.7 (#211, qui en dépend).
- **Post-commit (correctif fondamental)** : aucun hook post-commit n'existe (`shared/events.py` in-transaction only ; `dispatcher.py:380` reporte le delivery). À **concevoir** via listener `after_commit` (gabarit `accounts/service/setup.py:154`) — ne jamais diffuser depuis l'intérieur de la transaction (rollback → event fantôme).
- **Bornes de disponibilité** : plafond connexions/user + fermeture à l'expiration du token = critères (sinon OOM/slow-loris). **Rate-limit** `POST /sse/token` → câblé sur S02.5 (#73) ; en attendant, plafond + TTL sont les mitigations.
- **Token (ADR 0016)** : `jwt_secret` partagé → l'**audience est l'unique cloisonnement** ; `verify_sse_token` impose `audience`/`issuer` + refuse l'absence de `aud`. « Révocation rapide » = expiration 5 min (JWT stateless).
- **Import-linter** : sommet = `mcp` (pas `sync`) → placer `sse` dans la couche `sync | savings` ; `2-sse` mirror `2-sync` + contrats 5/6 ; **pas** de second-hop `notifications.public` (surface vide → casse `unmatched_ignore_imports_alerting`).
- **Streaming** : `StreamingResponse` natif (pas de dép `sse-starlette`) → gérer à la main format SSE + heartbeat + **désinscription au disconnect** (piège n°1 du broadcaster in-memory).
- **Buffer in-memory** (mono-process : multi-worker → backplane futur) ; `pending_actions` durable (ADR 0003, inexistante) = concern séparé.
