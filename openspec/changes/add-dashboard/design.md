## Context

Voir proposal.md — Why. Les données du foyer sont déjà répliquées en base locale par PowerSync ;
aucun écran ne les lit encore. Le pipeline de lecture réactif existe déjà côté client
(`use-account-balance`, `use-transactions`, `use-debts-for-current-user`) : facteurs de requête purs
`(db, args) → query` dans le module drizzle, exposés par des hooks `useQuery(toCompilableQuery(…))`.
Ce change est la première composition de bout en bout de ce pipeline, réutilisée par les écrans MVP
suivants.

## Goals / Non-Goals

**Goals :**
- Composer les quatre widgets en lecture seule sur la route `/`, entièrement offline-first.
- Poser les briques réutilisables (`Skeleton`, `Progress`, `formatCents`) et les facteurs de requête
  purs neufs.
- Rester dans le patron réactif existant, sans introduire de nouveau mécanisme de lecture.

**Non-Goals :**
- Toute écriture depuis le dashboard (les CTA des états vides naviguent, ils n'ouvrent pas de
  formulaire).
- Solde prévisionnel/projeté (MVP = solde réel seul), widgets configurables/réordonnables, épargne /
  récurrences / pointage.
- Piloter la réactivité PowerSync à travers un rendu dans les tests (différé — ne pas la simuler).

## Decisions

- **Lecture via facteurs de requête purs + hooks `useQuery`** — c'est le patron réactif déjà en place ;
  on ne réinvente rien. La couture de test principale est ce facteur pur (testé contre un SQLite
  in-memory réel chargé du DDL généré).
- **Dettes lues depuis la projection `debts` synchronisée** — **ADR-0002** (dettes = projection
  serveur) : le client n'agrège que le net par contrepartie, il ne recalcule pas. Le masquage
  débiteur est déjà porté par la projection (**ADR-0003**).
- **Solde réel = somme des splits `confirmed` non annulés** (réutilise `selectAccountBalance`,
  **ADR-0008** mono-devise) : agrégation d'une source synchronisée, pas une re-dérivation de
  projection serveur — il n'existe aucune table de soldes.
- **Consommation budget calculée côté client** — la consommation n'est **pas** synchronisée (service
  serveur, **ADR-0017** dépense confirmable vs consommation). Le MVP l'agrège depuis les splits
  `confirmed` sur le sous-arbre de catégories du budget (récursion `parent_id`, FR-6) dans sa
  période. Divergence possible avec la sémantique serveur → voir Open Questions.
- **Intention d'interface** portée par `docs/ui/` (screens-dashboard + design-system, déjà validés) —
  non dupliquée ici.

### Décisions de test

- **Couture principale : les facteurs de requête/agrégation purs** du module drizzle, testés contre un
  SQLite in-memory réel chargé du DDL généré (patron `client/src/lib/drizzle/queries.test.ts`,
  `@vitest-environment node`) — couvre le calcul (solde, dette nette, consommation, tri/limite) au
  plus haut, sans mock. Non couvert ici : la réactivité rendue.
- **Couture composant : les widgets** testés en isolant `useQuery` (mock `@powersync/react` →
  fixtures) ou en stubbant les hooks de domaine (patron
  `client/src/features/setup/setup-form.test.tsx`) — couvre présentation, états
  (vide/erreur/skeleton), formatage, signe+couleur+icône.
- **Aucune couture ne pilote la réactivité PowerSync** à travers un rendu (différée) — ne pas la
  simuler.
- **Prior art** : `client/src/lib/drizzle/queries.test.ts`,
  `client/src/hooks/use-account-balance.test.tsx`, `client/src/features/setup/setup-form.test.tsx`,
  et `client/tests/render.tsx` (`renderWithProviders`).

## Risks / Trade-offs

- [Consommation budget client ≠ serveur] → le calcul client peut diverger de la sémantique serveur
  (dépense confirmable vs consommation). Mitigation : périmètre MVP assumé, divergence traitée par un
  candidat ADR (Open Questions) avant d'envisager une projection synchronisée.
- [`userId` courant pour les dettes] → la vraie couche auth dépend de S14.6. Mitigation : le hook
  prend `userId` en entrée, la résolution est hors périmètre.

## Migration Plan

Sans objet — aucune migration de données, aucun changement de schéma serveur ; lecture seule de
tables déjà synchronisées.

## Open Questions

- **Consommation budget : projection serveur synchronisée vs recalcul client ?** Candidat ADR déposé.
  Reportable sans changer les specs ni le découpage de ce change (le MVP calcule côté client) ; à
  trancher avant d'industrialiser la consommation.
