# Écrans — Authentification & onboarding

Écrans **publics** (rendus nus, sans la coque/nav, centrés). Présupposent `design-system.md`.
Login et Setup **existent déjà** (livrés en S14.6) — décrits ici pour cohérence et re-maquettage.

---

## Connexion

- **Route** : `/login` — public.
- **Objectif** : se connecter au foyer (email + mot de passe).
- **Accès** : point d'entrée par défaut ; on y est redirigé si non authentifié.

### Anatomie
```
        ┌──────────────────────────────┐
        │           Connexion          │   (titre)
        │  Email      [____________]   │
        │  Mot de passe [__________]   │
        │  [ Se connecter ]            │   (bouton primaire, pleine largeur)
        │  (message d'erreur si échec) │   role="alert"
        └──────────────────────────────┘   carte centrée verticalement/horizontalement
```

### Données affichées
- Champs : **Email** (type email), **Mot de passe** (type password).

### États
- **Soumission** : bouton désactivé + libellé d'attente ; champs verrouillés.
- **Erreur** : message générique **« Identifiants invalides. »** (`role="alert"`), bouton réactivé.

### Interactions & flux
- Soumettre → si OK, redirection vers `/` (tableau de bord). Si échec, message générique.

### Validation & règles
- Anti-énumération : **même message** pour mauvais email, mauvais mot de passe, compte désactivé.
  Ne jamais distinguer.

### Copy FR (existant — réutiliser)
- Titre « Connexion » · « Email » · « Mot de passe » · bouton « Se connecter » · erreur
  « Identifiants invalides. ».

### Accessibilité
- Labels reliés aux champs ; erreur `role="alert"` ; focus initial sur l'email.

---

## Configuration (premier administrateur)

- **Route** : `/setup` — public, **mais à usage unique** (verrou après init).
- **Objectif** : amorcer le foyer en créant le **premier administrateur** (lock-after-init).
- **Accès** : seulement tant qu'aucun foyer n'est initialisé ; sinon rediriger vers `/login`.

### Anatomie
```
        ┌──────────────────────────────┐
        │        Configuration         │
        │  Nom du foyer  [__________]  │
        │  Nom affiché   [__________]  │
        │  Email         [__________]  │
        │  Mot de passe  [__________]  │  (≥ 12 caractères)
        │  [ Créer le premier administrateur ] │
        └──────────────────────────────┘
```

### Données saisies
- **Nom du foyer**, **Nom affiché** (display_name), **Email**, **Mot de passe** (min 12).

### États
- **Verrou** : si la configuration est déjà faite (course perdue) → toast
  **« Configuration déjà effectuée. »** + redirection `/login`.
- **Échec réseau** : **« Échec de la configuration. Réessayez. »**.

### Interactions & flux
- Soumettre → crée l'admin + auto-login → redirection `/`.

### Copy FR (existant — réutiliser)
- « Configuration » · « Nom du foyer » · « Nom affiché » · « Email » · « Mot de passe » ·
  « Créer le premier administrateur » · « Configuration déjà effectuée. ».

### Cas limites
- Deux personnes ouvrent `/setup` simultanément : une seule réussit, l'autre voit le verrou.

---

## Acceptation d'invitation

- **Route** : `/accept-invite?token=…` — **public** (l'invité n'a pas encore de session). À créer (S15.2).
- **Objectif** : un invité rejoint le foyer en définissant son nom + mot de passe.
- **Accès** : via un lien d'invitation (porte un token).

### Anatomie
```
        ┌────────────────────────────────────┐
        │      Rejoindre le foyer            │
        │  Invité : alice@exemple.fr (pré-rempli, non éditable) │
        │  Nom affiché   [______________]    │
        │  Mot de passe  [______________]    │  (≥ 12)
        │  [ Rejoindre le foyer ]            │
        └────────────────────────────────────┘
```

### Données affichées
- **Email de l'invité** (pré-rempli depuis le token, **lecture seule**), **expiration** éventuelle.
- Saisie : **Nom affiché**, **Mot de passe**.

### États
- **Chargement** : pendant la lecture du token (preview).
- **Token invalide / expiré (410)** : message clair **« Cette invitation a expiré ou n'est plus
  valide. »** + pas de formulaire (proposer de contacter un administrateur du foyer).
- **Soumission** : bouton désactivé.

### Interactions & flux
- À l'ouverture : lire le token → afficher l'email pré-rempli (ou l'erreur d'expiration).
- Soumettre → crée le compte (rôle **member**) + connexion → redirection `/`.

### Validation & règles
- Le **rôle est toujours `member`** (la promotion admin est un acte séparé) — ne pas proposer de
  choix de rôle.
- Invitation valide **7 jours** ; révocable/régénérable côté admin (un ancien lien devient invalide).

### Copy FR
- Titre « Rejoindre le foyer » · « Nom affiché » · « Mot de passe » · bouton « Rejoindre le
  foyer » · erreur expiration ci-dessus.

### Cas limites
- Lien déjà utilisé / révoqué / régénéré → même écran d'expiration (ne pas distinguer le motif).
