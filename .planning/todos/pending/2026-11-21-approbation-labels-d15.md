---
title: Revenir aux labels GitHub pour l'approbation humaine (D-15, remplace D-14)
created: 2026-11-21
source: décision de sebc-dev au checkpoint de la tâche 1 du plan 01-07 (/gsd-execute-phase 1)
resolves_phase: 1
priority: high
---

## Décision (2026-11-21)

`sebc-dev` revient au mécanisme de D-02 : l'approbation humaine (`gate-change-approved`, `deps-approved`) est un **label GitHub** posé par `sebc-dev` après le dernier commit de la PR, vérifié par la CI (événements `labeled`, `actor.login` dans une allowlist versionnée, label posé après le dernier commit, retiré à chaque push).

Risque accepté en connaissance de cause : l'agent détient le jeton `gh` de `sebc-dev`, si bien qu'un label posé par l'agent est indiscernable d'un label humain. La barrière contre l'auto-approbation repose sur les règles deny de l'agent (labels, API en écriture, fusion) et sur la garde Bash (plan 01-06), pas sur une preuve cryptographique. À documenter comme résiduel dans `docs/quality-gate.md`.

Une clé `ed25519-sk` est disponible : la signature matérielle (D-14) reste une option de durcissement ultérieure.

## Méthode retenue

Replanifier après la vague 4 (01-05, 01-06, 01-08 fusionnés ; 01-07 non exécuté, rien committé) par une seule passe `/gsd-plan-phase 1` :
- consigner D-15 dans `01-CONTEXT.md` (D-14 marqué remplacé) ;
- réécrire 01-07 en juge d'approbation par labels, en **conservant le schéma de `reports/approvals.json`** et sa CLI, consommés par 01-06 (intégrité) et 01-08 (deps-guard, verdict) ;
- ajuster 01-12 (cas d'auto-test liés à la signature) et 01-14 (plus d'enrôlement de clé ni de `allowed_signers` ; règles deny et scénarios D-07b par labels) ;
- dans la même passe, insérer le plan SonarQube (voir `2026-11-21-sonarqube-community-homelab.md`).
