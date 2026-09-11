# Run du ticket 02 (DebtSummary) avorté — agent absent du registre de session

Portée : add-dashboard · ticket 02
Ouvert le 2026-09-11 · branche `impl/debt-summary-02` · HEAD `c647ad1`

## Objectif
Faire aboutir `/scd-spec-dev:run add-dashboard 02` — le workflow `implement-ticket` s'est arrêté sur
une erreur d'outillage, pas sur un verdict du cycle.

## Contexte à charger
à lire      `openspec/changes/add-dashboard/tickets/02-debt-summary.md` — le contrat du ticket (22 l.)
à lire      `openspec/changes/add-dashboard/proposal.md` — le change que ce ticket sert

## Acquis
- J'avais résolu la base sans stacking : la dépendance 01 est ancêtre de `origin/main`, et j'avais
  armé `oldBase = impl/coque-balance-panel-01` pour le rebase préventif.
- Le workflow s'est arrêté en phase `Preflight`, **avant toute écriture** : la branche posée ne porte
  aucun commit, et aucune PR n'a été ouverte.
- J'ai identifié la cause : le registre d'agents de la session ne connaissait que les 26 agents de la
  version `0.2.0` du plugin, tandis que le script lancé venait de `0.6.2`. Les deux agents introduits
  en `0.6.0` — `escalation-triage` et `test-edit-validator` — étaient présents sur disque mais absents
  du registre. Un plugin mis à jour en cours de session ne recharge pas ses agents.

Sortie d'erreur, non tronquée :

```
Error: agent({agentType}): agent type 'scd-spec-dev:escalation-triage' not found. Available agents: claude, claude-code-guide, Explore, general-purpose, Plan, scd-spec-dev:architecture-reviewer, scd-spec-dev:branch-setup, scd-spec-dev:change-reviewer, scd-spec-dev:chantier-reader, scd-spec-dev:cleanliness-reviewer, scd-spec-dev:conventions-reviewer, scd-spec-dev:coverage-reviewer, scd-spec-dev:error-handling-reviewer, scd-spec-dev:fix-applier, scd-spec-dev:implementer, scd-spec-dev:integrity-reviewer, scd-spec-dev:pr-author, scd-spec-dev:pr-describer, scd-spec-dev:progress-recorder, scd-spec-dev:quality-advisor, scd-spec-dev:quality-analyzer, scd-spec-dev:quality-fixer, scd-spec-dev:rebaser, scd-spec-dev:relander, scd-spec-dev:review-context, scd-spec-dev:review-validator, scd-spec-dev:security-reviewer, scd-spec-dev:test-validator, scd-spec-dev:test-writer, scd-spec-dev:ticket-briefer, scd-spec-dev:verifier, statusline-setup
    at io (/$bunfs/root/chunk-x2v1mp3q.js:69:9229)
    at async <anonymous> (/$bunfs/root/chunk-9wa0ka8p.js:61:18372)
    at async <anonymous> (/$bunfs/root/chunk-x2v1mp3q.js:69:8015)
    at async <anonymous> (/$bunfs/root/chunk-6rvvk9vd.js:248:594)
    at processTicksAndRejections (native:7:39)
```

## Prochaine étape
Redémarrer Claude Code pour que le registre recharge les agents du plugin, puis relancer
`/scd-spec-dev:run add-dashboard 02`.

## Écarté
- Reprendre par `resumeFromRunId` — la reprise ne survit pas à la session, et c'est précisément la
  session qu'il faut renouveler pour corriger le registre.
- Lancer le workflow de la version `0.2.0`, dont le registre de la session connaissait les agents —
  cette version n'a pas la phase `Preflight`, le run aurait écrit du code sans le triage d'escalade.
