# Écrans — Dettes & règlements

Présuppose `design-system.md`. Routes **protégées** sous `/debts`. Une **dette** est orientée
(`from → to`), en **lecture seule** côté client (projection serveur). Elle naît soit d'un
**excédent budgétaire** sur compte commun, soit d'une **demande de partage** sur compte personnel.
On l'apure par un **règlement** (settlement) multi-lignes.

## Rappels domaine (essentiels pour l'UX)

- **Origine d'une dette** : `shared_account_overflow` (excédent sur compte commun) ou
  `personal_share_request` (demande explicite).
- **Solde restant** d'une dette = `montant − Σ lignes de règlement` (pas d'état stocké sur la dette).
- **Masquage côté débiteur** : le débiteur **ne voit pas** la transaction source (`source_transaction_id`)
  ni le compte d'origine — c'est **normal** (champs NULL côté client). Ne rien afficher de « manquant ».
- **Demande de partage** : porte un **libellé court** (≤100 car.) écrit par le demandeur ; c'est ce
  que voit le débiteur (pas le détail de la transaction).

---

## Dettes (vue principale)

- **Route** : `/debts` (option `?with=user_id` pour filtrer sur une contrepartie). **Objectif** :
  voir qui doit quoi, par contrepartie, et régler.

### Anatomie
```
┌──────────────────────────────────────────────────────────────┐
│ Dettes        ( ◉ On me doit   ○ Je dois )                   │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Alice                              vous devez 50,00 €  →  │ │
│ │   • Courses du 15/06 (libellé)        −30,00 €           │ │
│ │   • Cinéma (demande de partage)       −20,00 €           │ │
│ │   [ Régler avec Alice ]                                  │ │
│ │ Bob                                On vous doit 20,00 € → │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Données affichées
- **Onglets** : « On me doit » (créancier) / « Je dois » (débiteur).
- **Regroupement par contrepartie** : nom (`display_name`), **net** avec sens explicite, détail des
  dettes ouvertes (libellé court ou « Excédent — {compte/période} » selon l'origine, montant, restant).
- Côté débiteur : afficher le **libellé court** de la demande de partage, **jamais** la transaction source.

### États
- **Vide** : « Aucune dette. » (ton neutre — c'est une bonne nouvelle).
- Une dette **entièrement réglée** disparaît (restant = 0).

### Interactions & flux
- `[Régler avec {contrepartie}]` → écran **Régler des dettes** (sélection multiple).
- Depuis une **transaction personnelle** (écran transactions) : action **« Demander un partage »**.

### Copy FR
- « Dettes » · « On me doit » / « Je dois » · « vous devez » / « On vous doit » · « Régler avec … ».

---

## Demander un partage (depuis une transaction personnelle)

- **Objectif** : le propriétaire d'un **compte personnel** matérialise une dette vers une autre
  personne du foyer.

### Anatomie
```
  Demander un partage
  Transaction : Cinéma — 40,00 € (15/06)   (contexte, côté demandeur)
  Demander à   [ Alice ▼ ]
  Quote-part   [====●====] 50 %   →  18,00 € ... (calcul affiché)
  Libellé      [ Cinéma entre amis ]   ( ≤ 100 caractères )
  [ Annuler ]  [ Envoyer la demande ]
```

### Données saisies
- **Destinataire** (`requested_from`, membre du foyer), **quote-part** (ratio → montant calculé
  affiché), **libellé court** (≤100 caractères, c'est ce que verra le débiteur).

### Validation & règles
- Libellé : ≤100 caractères, caractères courants (ASCII/Latin-1).
- La somme des quote-parts des dettes dérivées d'une transaction = 100 % (si plusieurs demandes).
- Une demande est **révocable** (tant que non réglée).

### Copy FR
- « Demander un partage » · « Demander à » · « Quote-part » · « Libellé » · « Envoyer la demande ».

### Cas limites
- Côté **demandé** : la dette apparaît avec le libellé + montant ; **pas** de détail de la
  transaction source.

---

## Régler des dettes

- **Objectif** : apurer une ou plusieurs dettes ouvertes avec une contrepartie (règlement multi-lignes).

### Anatomie
```
  Régler avec Alice          Total dû : 50,00 €
  Dettes ouvertes :
   ☑ Courses du 15/06         restant 30,00 €   [ 30,00 € ]
   ☑ Cinéma                   restant 20,00 €   [ 20,00 € ]
  ── Total réglé : 50,00 € ──
  Type de règlement :
   ◉ Virement interne (lié à une transaction)   [ choisir la tx… ]
   ○ Virement externe
   ○ Compensation comptable (sans flux)
  Date    [ 15/06/2026 ]
  Note    [ (optionnel) ]
  [ Annuler ]  [ Enregistrer le règlement ]
```

### Données saisies
- **Sélection multiple** de dettes ouvertes + **montant à régler par dette** (≤ restant de chaque,
  > 0).
- **Type** : **Virement interne** (lié à une Transaction — sélectionner laquelle),
  **Virement externe**, **Compensation comptable** (sans flux).
- **Date**, **Note** (optionnelle).

### Validation & règles (**ferme**)
- Chaque ligne : **montant > 0** et **≤ solde restant** de la dette.
- **Virement interne** → exige une **transaction liée** ; sinon (externe/virtuel) → pas de lien.
- Après règlement, le **restant** de chaque dette diminue (zero-sum préservé) ; une dette à 0
  disparaît de la liste.

### Copy FR
- « Régler avec … » · « Dettes ouvertes » · « Total réglé » · « Virement interne » / « Virement
  externe » / « Compensation comptable (sans flux) » · « Date » · « Note » · « Enregistrer le
  règlement ».

### Accessibilité
- Cases à cocher labellisées par la dette ; total recalculé annoncé (`aria-live`).

### Cas limites
- Régler partiellement une dette : restant non nul → reste affichée avec le nouveau restant.
- Compensation croisée (A doit à B, B doit à A) : le type **Compensation comptable** apure sans flux.
