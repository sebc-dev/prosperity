---
title: Intégrer SonarQube Community (homelab) à la gate, en advisory
created: 2026-11-21
source: demande utilisateur pendant /gsd-execute-phase 1
resolves_phase: 1
priority: high
---

## Demande

Ajouter l'analyse SonarQube Community hébergée sur le homelab (serveur cité « kfzser… », nom exact et URL à confirmer à la planification).

## Décisions déjà prises (2026-11-21)

- **Rôle : advisory, nightly / local.** Analyse lancée depuis le homelab (nightly ou à la demande), résultats consultés dans Sonar. Ne change pas le verdict de `pnpm quality` (déterministe) et ne bloque aucune PR.
- **Planning : plan inséré avant 01-14.** À planifier (`/gsd-plan-phase 1`) une fois les vagues en cours terminées et à jouer avant le verrou, tant que la configuration de la gate reste modifiable sans approbation signée (D-14).

## Points à trancher à la planification

- Hôte, URL, version de SonarQube Community, mode d'accès (tailnet ?) et gestion du jeton (jamais dans le dépôt public).
- Déclencheur : timer systemd sur le homelab, `sonar-scanner` lancé à la main, ou job nightly sur runner auto-hébergé (déconseillé pour du code de PR sur un dépôt public).
- Import des rapports existants (couverture `coverage/lcov.info`, ESLint JSON) pour éviter les doubles analyses.
- Recouvrement avec ESLint + sonarjs + jscpd déjà bloquants ; référence : ancien `docs/recherches/2026-09-12-quality-gate-sonar-sans-serveur.md`.
- Mise à jour de `docs/quality-gate.md` (plan 01-13) et de la liste des chemins protégés si un fichier de config Sonar entre dans le dépôt.
