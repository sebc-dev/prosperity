# Run du ticket 02 (DebtSummary) bloqué — l'autofix de la quality gate a effacé les tests

Portée : add-dashboard · ticket 02
Ouvert le 2026-09-11 · Actualisé le 2026-09-11 · branche `impl/debt-summary-02` · HEAD `5b7774d`

## Objectif
Faire aboutir `/scd-spec-dev:run add-dashboard 02` — deux runs arrêtés sur de l'outillage, jamais
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

## Prochaine étape
Décider comment relancer sans rejouer la panne : (a) relance franche du run après avoir remis l'arbre
propre (`git checkout -- . && git clean -fd client/src` puis `git rm --cached` du test vide) — le
test-writer réécrira les tests, et l'erreur lint se reproduira sûrement ; ou (b) signaler le bug
au plugin `scd-spec-dev` : le garde-fou du `quality-fixer` doit **restaurer** un test neuf (untracked
ou intent-to-add) à son contenu d'avant autofix, pas à l'index, et un lint dans un test neuf devrait
plutôt remonter au `test-writer` qu'à la gate. Puis `/scd-spec-dev:run add-dashboard 02`.

## Écarté
- `resumeFromRunId` — le cache rejouerait le `quality-fixer` à l'identique sur un arbre déjà mutilé.
- Réparer les tests à la main dans la session principale — hors contrat de `run` (elle n'écrit pas
  de code) ; la reprise passe par le workflow.
- Lancer le workflow `0.2.0` — sans phase `Preflight`, écarté au 1er run.
