# Run bloqué — ticket 01 « Coque du tableau de bord + BalancePanel »

Portée : add-dashboard · ticket 01
Ouvert le 2026-09-07 · Actualisé le 2026-09-07 · branche `impl/coque-balance-panel-01` · HEAD `8e50abb`

## Objectif
Faire aboutir le run `implement-ticket` du ticket 01 (mode `test`) jusqu'à la PR : le workflow
s'est arrêté en **`blocked-verify`** après la phase Verify, sans quality gate, sans review, sans
commit, sans PR.

## Contexte à charger
à lire      `openspec/changes/add-dashboard/tickets/01-coque-balance-panel.md` — le contrat (critères SC-01a…h, mode `test`)
à lire      `openspec/changes/add-dashboard/proposal.md` — le change servi

## Acquis
- Le workflow a produit, **non commité** sur la branche, 6 fichiers d'impl (`format.ts`,
  `queries.ts`, `use-visible-accounts.ts`, `skeleton.tsx`, `balance-panel.tsx`,
  `_authenticated/index.tsx`) et 5 fichiers de test (3 neufs, 2 préexistants modifiés :
  `queries.test.ts`, `root-layout.test.tsx`). Le travail n'est pas perdu.
- Le `verifier` (contexte frais) a attesté les 8 critères, rejoué la suite sur checkout isolé
  (180/180, deux exécutions) et sondé la neutralisation : il a jugé le `vi.mock` ajouté à
  `root-layout.test.tsx` comme une limite du harnais (le stub PowerSync partagé n'expose pas de db
  Drizzle), même motif que le mock préexistant de `use-current-user` dans ce fichier.
- Le blocage tient au **drapeau strict** `testsDiffEmpty=false` : en mode `test` (test-after),
  ajouter des tests dans un fichier de test préexistant est le contrat, mais la ceinture compare
  base→tête et remonte tout diff de test pour arbitrage humain.
- Le `test-validator` avait rendu `gaps` (non bloquant dans le workflow) : deux écarts moyens —
  (1) aucun test n'assert le montant formaté rendu par BalancePanel (SC-01f n'assert que la
  fraîcheur) ; (2) `use-visible-accounts.ts` est mocké dans 3 tests mais n'a aucun test de câblage,
  contrairement aux hooks voisins. Plus des suggestions de cas limites (zéro, négatif à milliers,
  solde à signes mixtes, `selectVisibleAccounts(db, '')`).

## Prochaine étape
Arbitrer le diff des deux tests préexistants (`git diff -- client/src/lib/drizzle/queries.test.ts
client/src/pages/root-layout.test.tsx`) : s'il est accepté, combler les deux gaps moyens puis
reprendre la chaîne quality gate → review → record → PR sur la branche existante.

## Écarté
- Relancer `/scd-spec-dev:run add-dashboard 01` tel quel — la branche existe déjà avec du travail
  non commité, `branch-setup` refuserait, et le `verifier` rendrait le même drapeau.
- Corriger la ceinture ici — la règle « diff de test vide en mode `test` » est un point à remonter
  au plugin `scd-spec-dev`, pas à contourner dans ce run.

## Sortie d'erreur (non tronquée) — `verify.beltPassed.evidence`
```
CHECKOUT PROPRE : base=8e50abb, tete=arbre de travail sur impl/coque-balance-panel-01. `git status --porcelain --untracked-files=all` ne montre QUE le travail du ticket (4 modifies + 7 non suivis), aucun residu etranger. Verification rejouee dans une copie ISOLEE (/tmp/claude-1000/-home-negus-projets-prosperity/c9eb0182-9b05-4787-b3a4-37c9f10492fd/scratchpad/verify/repo, node_modules symlinke), depot utilisateur laisse intact (git status identique avant/apres).

DIFF DES FICHIERS DE TEST (base->tete) = NON VIDE -> testsDiffEmpty=false. `git diff --stat 8e50abb` : queries.test.ts 49 +, root-layout.test.tsx 11 + => 57 insertions / 3 suppressions. Les 3 SEULES lignes supprimees sont : (1) `-import { selectAccountBalance, selectDebtsForUser, selectTransactions } from './queries'` remplacee par un import multi-ligne ajoutant selectVisibleAccounts ; (2) et (3) deux lignes de COMMENTAIRE de root-layout.test.tsx (« jusqu'au placeholder dashboard » -> « jusqu'au tableau de bord »). AUCUNE assertion existante retiree, affaiblie ni renommee. Les 2 fichiers nouvellement ajoutes de tests (format.test.ts, balance-panel.test.tsx, index.test.tsx) sont non suivis = tests NEUFS (test-after), attendu.

SONDAGE DE NEUTRALISATION (seul changement de comportement) : root-layout.test.tsx ajoute `vi.mock('@/hooks/use-visible-accounts', () => ({ useVisibleAccounts: () => ({ data: [], isLoading: false, error: undefined }) }))`. J'ai retire ce mock dans la copie isolee et rejoue -> ECHEC : `AssertionError: expected "error" to not be called at all, but actually been called 1 times` / `[TypeError: db.select is not a function]` / `The above error occurred in the <BalancePanelContent> component` (rattrape par BalanceErrorBoundary). Cause = LIMITE DU HARNAIS (le mock du singleton PowerSync n'expose pas de db Drizzle interrogeable par useQuery), pas un defaut produit masque ; motif identique au vi.mock('@/hooks/use-current-user') PREEXISTANT dans ce meme fichier, et documente en commentaire. Fichier restaure a l'identique ensuite (diff -q = RESTORED-IDENTICAL). Verdict : plomberie legitime, PAS neutralisation — mais le drapeau strict reste false et est remonte tel quel pour arbitrage humain.

REJEU DE testCommand `cd client && npm run test` (vitest run v4.1.8) sur checkout propre isole, DEUX executions consecutives identiques :
  Test Files  36 passed (36)
  Tests  180 passed (180)
  Duration  10.22s puis 10.15s
=> failed=0 sur MA sortie reelle.

INTEGRITE DE LA SUITE : aucun .skip/.only/.todo/xit/xdescribe dans les 5 fichiers declares (grep -> NONE). vite.config.ts n'exclut rien : include: ['src/**/*.test.{ts,tsx}', 'tests/**/*.test.ts']. Les 5 fichiers declares : 5 passed / 17 tests passed en --reporter=verbose. Copie isolee verifiee octet-pour-octet identique a l'arbre utilisateur sur les 11 fichiers impl+test (diff -q = IDENTIQUE).

NON-TAUTOLOGIE : queries.test.ts tourne en @vitest-environment node contre un SQLite in-memory REEL charge du DDL genere (pas de mock DB) ; selectVisibleAccounts est une vraie requete Drizzle (isNull(archived_at) AND (eq(owner_id,userId) OR inArray(id, sous-requete account_members))) ; Skeleton porte bien data-slot="skeleton" interroge par le test.

BRUIT NON BLOQUANT : index.test.tsx emet des avertissements React `An update to UserMenu / BalancePanelContent inside a test was not wrapped in act(...)` — n'echoue pas, mais passerait au rouge si ce test adoptait l'assertion anti-console.error du root-layout. Signale, non corrige (je ne repare pas).
```
