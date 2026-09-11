# Run du ticket 02 (DebtSummary) bloqué — la quality gate bute sur le format d'un test neuf

Portée : add-dashboard · ticket 02
Ouvert le 2026-09-11 · Actualisé le 2026-09-11 · branche `impl/debt-summary-02` · HEAD `591de7a`

## Objectif
Faire aboutir `/scd-spec-dev:run add-dashboard 02` — trois runs arrêtés sur de l'outillage, jamais
sur un verdict du cycle.

## Contexte à charger
à lire      `openspec/changes/add-dashboard/tickets/02-debt-summary.md` — le contrat du ticket (22 l.)
à lire      `openspec/changes/add-dashboard/proposal.md` — le change que ce ticket sert

## Acquis
- 1er run (agent hors registre) : résolu par un redémarrage de Claude Code — le registre a rechargé
  `escalation-triage` et `test-edit-validator`. Voie confirmée.
- 2e run (`wf_f04035cb-0e5`) : statut **`blocked-quality-tests-touched`**. Preflight, impl (mode
  `test`), test-writer, test-validator (`ok`) et verifier étaient passés ; la branche était rejointe
  en reprise (`exists:true`), rebase no-op. Le code de prod est resté **non commité** sur la branche.
- Cause trouvée : le check `frontend-lint` échouait sur UNE erreur dans le test neuf
  (`@typescript-eslint/no-unnecessary-type-assertion`, `debt-summary.test.tsx:47`). L'autofix
  `eslint --fix` l'a corrigée — donc a touché un test — et le garde-fou du `quality-fixer` a fait
  `git checkout --` sur les deux fichiers de test. Or le `verifier` avait fait `git add -N` dessus :
  `debt-summary.test.tsx` (neuf) a été ramené à son blob d'index **vide**, et `queries.test.ts` à sa
  version `HEAD`. Les tests écrits par le `test-writer` ont été **perdus** ; le fixer a tenté de les
  recréer de mémoire puis a renoncé (`git rm --cached` + `rm`). Reste un `debt-summary.test.tsx`
  vide en intent-to-add.
- Le contenu original du test survit dans la transcription du `test-writer` (appel `Write`) :
  `~/.claude/projects/-home-negus-projets-prosperity/a9548820-…/subagents/workflows/wf_f04035cb-0e5/agent-abc4d899de6470e4a.jsonl`.

Sortie du fixer, non tronquée :

```
{"applied":[],"residual":[{"checkId":"frontend-lint","severity":"blocking","status":"fail","reason":"autofix modifies test files (safety guard); cannot fix lint error in new test file without modifying it"}],"testsUntouched":false,"blockingResidual":1}
```

- 3e run (`wf_05cbd98c-e2e`, relance franche après `git stash -u` du code du 2e run → `stash@{0}`) :
  statut **`blocked-quality`**. Cette fois les tests ont survécu (`testsUntouched:true`), mais le
  même check `frontend-lint` bloque sur `prettier --check` du test neuf `debt-summary.test.tsx` —
  et le fixer refuse l'autofix parce qu'il toucherait un test. Sortie non tronquée :

```
{"applied":[],"residual":[{"checkId":"frontend-lint","severity":"blocking","status":"fail","reason":"autofix modifies test files (debt-summary.test.tsx, queries.test.ts) — test integrity constraint prevents autofix"}],"testsUntouched":true,"blockingResidual":1}
```

- Diagnostic consolidé : un défaut lint/format **dans un test neuf** est structurellement hors de
  portée de la gate (elle n'a pas le droit d'y toucher) et personne en amont ne formate les tests.
  Sans applier de projet, ce ticket rejouera la panne à chaque run.

## Prochaine étape
J'allais déclarer l'**applier du projet** via `/scd-spec-dev:quality-agents` (top-level `applier`
dans `.claude/quality.json`, seul agent du cycle autorisé à éditer les tests, borné par l'additivité
et audité par `test-edit-validator`) — un `prettier --write` sur un test est additif-neutre. Puis
relancer `/scd-spec-dev:run add-dashboard 02` (le code du 3e run est resté non commité, staged, sur
la branche ; `stash@{0}` porte celui du 2e — à jeter, le 3e le remplace).

## Écarté
- `resumeFromRunId` — le cache rejouerait le `quality-fixer` à l'identique.
- Relancer une 4e fois sans rien changer — la panne est déterministe.
- Corriger le plugin (`quality-fixer`) d'abord — vrai bug (garde-fou qui ramène un test neuf à
  l'index vide), mais la voie supportée pour ce projet est l'applier ; à signaler à part.
- Réparer les tests à la main dans la session principale — hors contrat de `run` (elle n'écrit pas
  de code) ; la reprise passe par le workflow.
- Lancer le workflow `0.2.0` — sans phase `Preflight`, écarté au 1er run.
