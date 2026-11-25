---
gsd_state_version: "1.0"
current_phase: 2
current_phase_name: Connecteur Claude et identité du foyer
status: planning
stopped_at: Phase 01 complete, ready to plan Phase 2
last_updated: "2026-11-25T19:14:56.960Z"
last_activity: 2026-11-25
last_activity_desc: "Phase 01 shipped as PR #308"
state_head: 45c4472ab13c088907fef94f8a844a4c95415991
progress:
  total_phases: 9
  completed_phases: 1
  total_plans: 15
  completed_plans: 15
  percent: 11
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-25)

**Core value:** Chaque membre du foyer peut, en une phrase à Claude, saisir une dépense ou voir l'état exact et à jour des finances du foyer (soldes, budgets, dettes). Les chiffres viennent d'un backend qui calcule juste et ne montre à chacun que ce qu'il a le droit de voir.
**Current focus:** Phase 2 — Connecteur Claude et identité du foyer

## Current Position

Phase: 2 — Connecteur Claude et identité du foyer
Plan: Not started
Status: Ready to plan
Last activity: 2026-11-25 -- Phase 01 shipped as PR #308

Progress: [█░░░░░░░░░] 11%

## Performance Metrics

**Velocity:**
- Total plans completed: 15
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 15 | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Le journal complet des décisions est la table Key Decisions de PROJECT.md. Décisions récentes qui pèsent sur le travail en cours :

- [Phase 1] Quality gate livrée et verrouillée : statut `quality` publié par le juge hors PR (`prosperity-gate`), approbation par label D-15 (résiduel du jeton partagé accepté, T-01-27), Sonar advisory nightly sur kfzcore. UAT 3/3, sécurité 68/68 menaces closes.
- [Init] Stack TypeScript mono-langage validée : Node 26, TS 6.0.3 épinglé, SDK MCP v2, `oidc-provider`, PostgreSQL 18, Kysely, pg-boss.
- [Init] La quality gate (phase 1) précède toute ligne de domaine. Le spike connecteur + OAuth de bout en bout, avec un second compte membre, est la sortie obligatoire de la phase 2.
- [Init] Canal de confirmation en MCP Apps dès la v1 (outils `visibility: ["app"]`). Le spike a lieu tôt (phase 2) ; s'il échoue, la page d'approbation hors bande est le repli documenté (POL-04, phase 5).
- [Init] DSP2 (Enable Banking) reste en v1, en dernière phase, après l'import fichier dont il réutilise la dédup et le pointage.
- [Init] Toutes les options passent en v1 : récurrences, photo de ticket, void par lot, CSV, mémoire de catégorisation, `risk_based`, double accord, revue mensuelle, simulations, projection d'épargne.

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2+] Démarrer tôt l'enregistrement de l'application Enable Banking (mode restricted production), qui a des délais, et collecter des relevés OFX/CSV anonymisés des banques du foyer pour les spikes parseurs.
- [Phase 1] Stryker : ne pas committer le fichier d'incrémental (bug #6004).
- [Phase 1] Résiduels sécurité non bloquants R1-R7 et drapeau `local-container-exec` à traiter ou accepter (voir 01-SECURITY.md) ; 01-VALIDATION.md encore en draft (audit Nyquist non fait).
- [Phase 2] URL CIMD de claude.ai non documentée. Le rendu MCP Apps sur connecteur custom est peu fiable (ticket ext-apps #671) et `_meta.ui.visibility` n'est pas vérifié. `_meta.ui.domain` dérive de l'URL : figer l'URL publique dès la phase 2.
- [Phase 3] RLS avec pool (`SET LOCAL` par transaction avec Kysely) et `Temporal` dans TS 6.0.3 sont à prototyper.
- [Phase 8] Disponibilité de `listTools().fileArgs` chez les lecteurs du foyer : à vérifier avant de construire l'import.
- [Research] Des exemples Python (ruff, pyright, import-linter, mutmut, Hypothesis) subsistent dans ARCHITECTURE.md et PITFALLS.md : les traduire vers les outils TS retenus pendant la recherche de phase.
- [Produit] Les artefacts `mcp` exigent un plan claude.ai payant pour chaque membre. La confidentialité vis-à-vis du fournisseur du modèle (M10) demande une décision écrite au niveau du foyer.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-25T18:30:00Z
Stopped at: Phase 01 complete, ready to plan Phase 2
Resume file: None
