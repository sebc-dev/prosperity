# Mono-devise V1 via verrou `household.base_currency`, modèle `Money` multi-devise prêt

L'invariant transversal #3 interdit l'arithmétique cross-devise, mais le périmètre fonctionnel V1 (DSP2 français, foyer franco-français) est de facto mono-EUR — autoriser dès la V1 un compte en devise étrangère ouvrirait des questions UX (agrégation cross-devise sur le dashboard, conversion pour le `summary`, dettes mixtes) qui ne paient pas. Nous décidons de verrouiller la V1 à une devise unique au niveau du foyer via `household.base_currency` (valeur fixe `"EUR"` en V1), tout en gardant le **type `Money` multi-devise au domaine** pour ne pas avoir à toucher le modèle lors d'une ouverture future. La validation au niveau `accounts.create()` rejette toute création de compte dans une autre devise.

## Considered Options

- **(A) Affichage par devise sans agrégation** dès V1 : prématuré, complexifie tous les écrans agrégateurs pour un besoin qui n'existe pas encore.
- **(B) Pin EUR via `household.base_currency` (retenu)** : zéro coût UX en V1, ouverture post-V1 = suppression du verrou + adaptation des écrans agrégateurs, sans migration de données.
- **(C) Devise pivot avec taux de change manuel** : over-engineered V1, invite des bugs subtils sur les agrégats temporels.

## Consequences

- Le dashboard, `summary`, `analyze_spending` agrègent librement en garantissant l'homogénéité de devise — aucune ligne de conversion dans le code.
- Les écrans qui agrègent (graphiques 12 mois, dettes par contrepartie, total patrimoine) doivent être identifiés comme "à adapter" en post-V1 si on ouvre le multi-devise.
- Le type `Money` reste fidèle à son contrat "pas d'opération cross-devise" : l'invariant tient au niveau domaine indépendamment du verrou foyer.
- Documenter dans le spec hors-périmètre V1 : compte en devise étrangère, agrégation cross-devise, taux de change.
