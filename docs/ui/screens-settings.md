# Écrans — Réglages

Présuppose `design-system.md`. Route **protégée** `/settings`, organisée en **onglets**. Certains
onglets sont **réservés aux administrateurs** (`role = admin`) — la nav/les onglets admin sont
**masqués** pour un member (masquage UI ; l'enforcement réel est serveur).

```
┌──────────────────────────────────────────────────────────────┐
│ Réglages                                                     │
│ [ Profil ] [ Foyer (admin) ] [ Invitations (admin) ]         │  ← Tabs
│ ────────────────────────────────────────────────────────────│
│ <contenu de l'onglet>                                        │
└──────────────────────────────────────────────────────────────┘
```

---

## Onglet — Profil (tout utilisateur)

- **Objectif** : gérer son identité et ses accès.

### Anatomie
```
  Profil
  Nom affiché   [ Alice ]                         [ Enregistrer ]
  Email         [ alice@exemple.fr ]   [ Modifier l'email ]   (ré-authentification requise)
  Mot de passe  ••••••••              [ Changer le mot de passe ] (ré-authentification requise)
```

### Données / actions
- **Nom affiché** : éditable directement.
- **Email** : modification **sensible** → exige une **ré-authentification** (re-saisie du mot de
  passe) avant validation.
- **Mot de passe** : changement → exige **ré-authentification** ; nouveau mot de passe ≥ 12.

### Validation & règles
- Toute action sensible (email, mot de passe) passe par un **dialog de ré-authentification**.
- Messages génériques en cas d'échec d'auth (« Mot de passe incorrect. »).

### Copy FR
- « Profil » · « Nom affiché » · « Modifier l'email » · « Changer le mot de passe » ·
  « Ré-authentification requise » · « Enregistrer ».

---

## Onglet — Foyer (admin uniquement)

- **Objectif** : paramètres du foyer.

### Anatomie
```
  Foyer
  Nom du foyer      [ Foyer Martin ]              [ Enregistrer ]
  Devise            EUR   (lecture seule en V1)
  ── Journal d'audit (lecture) ──
   15/06 10:32  Alice a invité bob@exemple.fr
   14/06 18:01  Alice a créé le compte « Commun »
```

### Données / actions
- **Nom du foyer** : éditable.
- **Devise de base** : **lecture seule** en V1 (mono-devise, EUR).
- **Journal d'audit** (lecture) : liste horodatée d'actions admin (qui / quoi / quand), en FR.

### Validation & règles
- Onglet **invisible** pour un member. Le journal est en **lecture seule**.

### Copy FR
- « Foyer » · « Nom du foyer » · « Devise » · « Journal d'audit ».

---

## Onglet — Invitations (admin uniquement)

- **Objectif** : inviter de nouvelles personnes et gérer les invitations en cours.

### Anatomie
```
  Invitations                                   [ + Inviter ]
  En attente :
   bob@exemple.fr     expire dans 6 j   [ Régénérer ] [ Révoquer ]
   chloe@exemple.fr   expire dans 2 j   [ Régénérer ] [ Révoquer ]
```

### Données affichées
- Liste des invitations **en attente** : **email**, **expiration** (relative, ex. « expire dans
  6 j »), actions **Régénérer** / **Révoquer**.

### Interactions & flux
- `[+ Inviter]` → saisie d'un **email** → crée une invitation (rôle **member** par défaut) et
  fournit un **lien à transmettre** (l'app n'envoie pas d'email en MVP — afficher/copier le lien).
- **Régénérer** : invalide l'ancien lien, en émet un nouveau (avertir : « L'ancien lien ne
  fonctionnera plus. »).
- **Révoquer** : annule l'invitation (le lien devient invalide).

### Validation & règles
- Rôle invité = **toujours member** (la promotion admin est un acte séparé) → ne pas proposer de
  rôle à l'invitation.
- Invitation valable **7 jours**.

### Copy FR
- « Invitations » · « Inviter » · « En attente » · « expire dans {n} j » · « Régénérer » ·
  « Révoquer » · « Copier le lien » · « L'ancien lien ne fonctionnera plus. ».

### Cas limites
- Email déjà membre / déjà invité : message clair (« Cette personne fait déjà partie du foyer / a
  déjà une invitation en cours. »).
- En MVP, **pas d'envoi d'email automatique** : l'admin **copie et transmet** le lien lui-même.
