# Application Finances Personnelles — Spécification des Features

> Synthèse fonctionnelle de l'application
> **Date** : mai 2026
> **Statut** : Spécification — arbitrages produit tranchés (v3, points ouverts résolus)

---

## 1. Vision

Application personnelle de gestion de finances pour un foyer (multi-utilisateurs adultes), permettant :

- L'agrégation automatique des comptes bancaires français (DSP2 via Enable Banking) et l'import manuel pour les comptes hors-périmètre (livrets, épargne).
- La saisie manuelle complète (transactions locales, ponctuelles ou récurrentes), avec pointage contre les transactions bancaires.
- La gestion partagée d'un budget familial avec suivi des dettes croisées entre conjoints.
- La projection de l'évolution des soldes (réel, prévisionnel, projeté) et de l'épargne (objectifs).
- L'usage offline-first sur Web et Android, avec synchronisation transparente.
- **L'accès agent via MCP** : Claude peut interroger et conseiller à partir des données du foyer.

**Philosophie produit** : tout est saisissable manuellement et tout est pointable. La connexion bancaire est une commodité, pas une dépendance bloquante. L'agent IA est un assistant, pas un automate autonome.

---

## 2. Utilisateurs cibles

| Persona | Description |
|---|---|
| **Adulte 1 (admin par défaut)** | Initie le foyer, configure les comptes, invite les autres membres |
| **Adulte 2 (co-administrateur)** | Saisit ses propres transactions, accède aux comptes communs, peut être promu admin |
| **(Futur) Adolescent** | Accès en lecture éventuel sur son compte personnel, hors MVP |
| **Claude (agent IA)** | Accède aux données via MCP, lecture seule en V1, écriture avec confirmation en V2 |

**Hors périmètre** : utilisation B2B, multi-foyer sur la même instance, grands volumes (>10 utilisateurs).

---

## 3. Vue d'ensemble des features

| # | Feature | Priorité | Complexité métier |
|---|---|---|---|
| F01 | Authentification multi-utilisateur sécurisée | MVP | Faible |
| F02 | Comptes personnels et communs | MVP | Moyenne |
| F03 | Droits et administration | MVP | Moyenne |
| F04 | Import de transactions bancaires (Enable Banking + OFX) | MVP | Moyenne |
| F05 | Création de transactions locales | MVP | Faible |
| F06 | Transactions récurrentes | MVP | Moyenne |
| F07 | Pointage transactions locales ↔ bancaires | MVP | **Élevée** |
| F08 | Gestion de budgets | MVP | Faible |
| F09 | Dettes entre utilisateurs | MVP | **Élevée** |
| F10 | Transactions non-budgétisées → dettes | MVP | **Élevée** |
| F11 | Dashboard multi-soldes (réel, prévisionnel, projeté) | MVP | **Élevée** |
| F12 | Gestion de l'épargne avec objectifs | V1 | Moyenne |
| F13 | Notifications (email, push, in-app, SSE) | V1 | Faible |
| F14 | Accès MCP pour Claude (read-only V1, write V2) | V1 | **Élevée** |

---

## 4. Détail des features

### F01 — Authentification multi-utilisateur

**Description**
Système d'authentification permettant à plusieurs utilisateurs adultes d'un même foyer d'accéder à l'application depuis Web et Android, plus accès agent via Personal Access Tokens (PAT) pour le MCP server.

**User stories**

- En tant qu'utilisateur, je veux me connecter avec email + mot de passe pour accéder à mon foyer.
- En tant qu'utilisateur, je veux rester connecté sur mon device pour ne pas resaisir mes identifiants.
- En tant qu'utilisateur, je veux pouvoir me déconnecter à distance d'une session sur un autre device.
- En tant qu'utilisateur, je veux générer un Personal Access Token pour autoriser Claude à interroger mes données via MCP.
- En tant qu'utilisateur, je veux pouvoir révoquer un PAT à tout moment et voir la date de dernière utilisation.
- En tant qu'utilisateur, je veux pouvoir choisir la durée de validité d'un PAT à sa création.
- En tant qu'utilisateur, je veux être alerté immédiatement si un PAT présente un comportement suspect, et qu'il soit désactivé automatiquement si le signal est sans ambiguïté.
- En tant qu'utilisateur, je veux disposer d'une vue claire de l'activité de mes PAT pour faire ma propre détection.

**Règles métier**

- Mot de passe haché en Argon2id (pwdlib).
- JWT access token (15 min) + refresh token (30 j, stocké en base, révocable).
- Pas d'inscription publique : création de compte uniquement par invitation d'un administrateur.
- 2FA optionnel (TOTP) — V1.

**Personal Access Tokens (PAT)**

- Préfixés (`pfa_` par exemple), hashés en base (jamais stockés en clair après génération).
- Hérite strictement des droits de l'utilisateur propriétaire — jamais plus, même si l'utilisateur est admin.
- **Nombre illimité de PAT par utilisateur**. Chaque PAT est nommé pour permettre l'identification (ex. "Claude Code local", "n8n daily report", "Claude.ai analyse").
- **Durée de vie paramétrable, défaut 1 an**. L'utilisateur choisit librement (1 jour à plusieurs années, ou sans expiration explicite avec révocation manuelle uniquement).
- **Scope V1** : `read_only` ou `read_write` au niveau du PAT entier. Granularité fine par tool prévue post-V1.
- Métadonnées : `name`, `scope`, `created_at`, `expires_at`, `last_used_at`, `last_used_ip`, `last_used_asn`, `revoked_at`, `revoked_reason`.

**Détection de compromission : heuristiques et politiques de réaction**

Principe directeur : **alerter ≠ désactiver**. La désactivation automatique est réservée aux signaux binaires et sans ambiguïté ; les signaux probabilistes déclenchent une alerte avec un bouton "Désactiver maintenant" dans la notification, laissant l'utilisateur trancher en un tap.

*Heuristiques V1 (Tier 1, 4 signaux)*

| Heuristique | Détail | Action |
|---|---|---|
| Plafond dur de rate limit | Au-delà de 60 req/min sur un PAT, requêtes rejetées (HTTP 429) | Containment, pas de désactivation |
| Tentatives d'appel hors scope | PAT en `read_only` qui appelle un tool d'écriture, ou tool inexistant : ≥ 3 tentatives en moins de 5 min | **Désactivation automatique** + push + email |
| Concurrence géographique impossible | Même PAT utilisé depuis deux IP géographiquement distantes (>500 km) en moins de 5 min, après whitelist des ASN connus (Anthropic, OVH si n8n self-hosted, Cloudflare egress, etc.) | **Alerte** ; désactivation seulement si confirmé par un second signal dans les minutes qui suivent |
| Burst soutenu | >30 req/min en moyenne sur 15 minutes consécutives | **Alerte**, pas de désactivation |

Ne s'applique qu'au transport HTTP pour les heuristiques basées sur l'IP — stdio (Claude Code local) n'a pas d'IP exposable.

*Heuristiques V1.5 (à activer après ≥ 1 mois de baseline réelle)*

- **Volume cumulé exfiltré sur 24h** au-delà d'un seuil calibré sur le p99 de l'usage réel (alerte). Borne la capacité d'extraction d'un PAT compromis indépendamment du débit instantané.
- **Première utilisation depuis un ASN inédit** (notification informative, agrégée par ASN pour limiter la fatigue). Désactivable dans les préférences.
- **Réveil d'un PAT dormant** (> 30 j sans usage) avec burst (alerte enrichie du contexte "dernier usage il y a N jours").
- **Pattern d'énumération massive** combiné à un autre signal (ex. nouveau ASN + énumération). Seul, trop ambigu pour générer une alerte.

*Heuristiques explicitement écartées pour ce use-case*

- **Profilage par tranche horaire** : volume trop faible pour produire des baselines statistiquement significatives. Faux positifs garantis sur usage humain irrégulier.
- **Géoloc avec blocage strict par pays (whitelist)** : Claude.ai opère depuis plusieurs régions cloud, blocage casse l'usage légitime.
- **Fingerprinting User-Agent / client MCP** : le même PAT peut légitimement être utilisé depuis Claude Code, Claude.ai et n8n. Bruit garanti.

*Notifications de sécurité*

- Toute désactivation automatique : push + email immédiats, canaux **non désactivables**.
- Toute alerte probabiliste : push (canal non désactivable pour les événements de sécurité) avec bouton **"Désactiver maintenant"** actionnable directement depuis la notification.
- La désactivation est révocable manuellement par l'utilisateur s'il confirme que l'usage était légitime (voyage, nouvel agent, etc.).

*Compléments structurels (plus efficaces que les heuristiques seules)*

- **Page "Activité de mes PAT"** dans l'app : dernière utilisation, ASN/IP, distribution des tools appelés, courbe d'usage, alertes en cours. La détection humaine en 30 secondes bat la majorité des heuristiques sur ce volume.
- **Cloudflare Access devant le MCP HTTP** (service tokens ou mTLS) en couche supérieure au PAT. Le PAT devient alors un second facteur applicatif, pas la seule défense. Réduit drastiquement la surface où la détection doit faire le travail seule.

*Calibration empirique*

Pendant les 2-3 premiers mois de mise en production, mesurer le **p95/p99 du débit légitime par tool** pour calibrer le seuil de "burst soutenu" sur l'usage réel plutôt qu'à l'aveugle. Les seuils des autres heuristiques Tier 1 sont assez génériques pour être posés en dur dès V1.

**Dépendances** : aucune (feature fondatrice).

---

### F02 — Comptes personnels et communs

**Description**
Modélisation des comptes financiers (courant, livret, épargne) avec deux types de propriété : personnel (un seul propriétaire) ou commun (plusieurs propriétaires avec quote-parts).

**User stories**

- En tant qu'utilisateur, je veux déclarer un compte courant personnel pour y suivre mes transactions.
- En tant que couple, nous voulons un compte commun où chacun peut saisir des transactions.
- En tant que propriétaire d'un compte commun, je veux que la quote-part par défaut soit 50/50 mais que je puisse ajuster la répartition au cas par cas sur chaque dette générée.

**Règles métier**

- Un compte personnel a un seul `owner_id`. **Un compte ne peut pas exister sans propriétaire** (contrainte d'intégrité dure).
- Un compte commun a une table `account_members` avec `user_id`, `default_share_ratio` (fractions sommant à 1, **50/50 par défaut** pour deux membres).
- La quote-part par défaut s'applique à la génération automatique des dettes ; **chaque dette créée peut être ajustée individuellement** après coup (cf. F09).
- Types de comptes supportés : courant, livret, épargne, espèces, crédit (carte de crédit, prêt).
- Chaque compte porte une `currency` (ISO 4217), stockage des montants en centimes entiers.
- Un compte peut être lié à une connexion bancaire Enable Banking (`bank_link_id` nullable) ou alimenté manuellement (OFX ou saisie pure).
- Suppression d'un utilisateur : ses comptes personnels deviennent inaccessibles. Option : transfert de propriété à un autre utilisateur via flow admin explicite (sinon le compte est archivé en lecture seule pour audit).

**Dépendances** : F01.

---

### F03 — Droits et administration

**Description**
Système de rôles strict : l'administrateur gère les **droits d'accès et l'enrôlement** des utilisateurs, mais n'a aucun accès aux **données financières** des comptes dont il n'est pas membre.

**User stories**

- En tant qu'admin, je veux inviter un nouvel utilisateur dans le foyer en envoyant un lien d'invitation.
- En tant qu'admin, je veux promouvoir un utilisateur en co-administrateur.
- En tant qu'admin, je veux révoquer l'accès d'un utilisateur sans supprimer ses transactions historiques (les données restent, l'accès est coupé).
- En tant qu'utilisateur, je veux la garantie que **même l'admin ne peut pas voir mes transactions personnelles**.

**Règles métier**

- Rôles : `admin`, `member`.
- Au moins un admin doit exister à tout moment (impossibilité de se rétrograder seul, blocage de la révocation du dernier admin).
- **Principe directeur** : *l'admin gère les droits, pas les données*.
- Permissions par compte personnel : **strictement propriétaire uniquement**, y compris pour l'admin. L'admin voit l'existence d'un compte dans une liste administrative (pour gérer le cycle de vie de l'utilisateur), mais ne voit ni transactions, ni soldes, ni détails.
- Permissions par compte commun : lecture, écriture, gestion des membres — accordées uniquement aux membres effectifs.
- **Pas de compte sans utilisateur** : on ne peut pas créer ou maintenir un compte orphelin.
- Audit log des actions d'administration (invitation, promotion, révocation, modification des membres d'un compte commun).
- Cette règle s'applique aussi au MCP (F14) : un PAT n'a jamais plus de droits que l'utilisateur auquel il appartient, même si cet utilisateur est admin.

**Dépendances** : F01, F02.

---

### F04 — Import de transactions bancaires

**Description**
Deux voies d'import : automatique via Enable Banking (DSP2, comptes courants) et manuelle via OFX (livrets, épargne hors-périmètre DSP2).

**User stories**

- En tant qu'utilisateur, je veux lier mon compte Société Générale via Enable Banking pour récupérer automatiquement mes transactions deux fois par jour.
- En tant qu'utilisateur, je veux importer un fichier OFX exporté depuis mon espace bancaire pour mon Livret A.
- En tant qu'utilisateur, je veux être averti 7 jours avant l'expiration de mon consentement bancaire (limite DSP2 de 180 jours).
- En tant qu'utilisateur, je veux que les imports routiniers sans anomalie passent sans friction, mais qu'un import suspect déclenche une preview avant validation.

**Règles métier**

- Connexions Enable Banking : Société Générale, Banque Populaire (par caisse régionale), BRED, autres ASPSP français supportés.
- Polling automatique 2× par jour (cron / APScheduler).
- Renouvellement de consentement = nouvelle SCA requise (Règlement UE 2022/2360).
- Déduplication des transactions importées par hash composite (date + montant + libellé + compte) — les IDs Enable Banking ne sont pas stables côté ASPSP français.
- Pas de stockage chez Enable Banking (modèle passthrough strict de leur côté).

**Politique d'import OFX : preview hybride conditionnel**

Auto-validation si **tous** ces critères sont remplis :

- Aucun doublon détecté (hash composite déjà connu)
- Encodage détecté avec confiance (BOM ou heuristique stable, windows-1252 / UTF-8)
- Toutes les transactions dans une fenêtre temporelle raisonnable (± 3 ans)
- Aucune transaction avec |montant| > 10 000€
- Volume < 50 transactions

Sinon : preview obligatoire avec mise en évidence des lignes problématiques. L'utilisateur peut corriger, ignorer ou tout valider. L'utilisateur peut forcer la preview même si tous les critères sont remplis (préférence configurable).

**Dépendances** : F02, F07.

---

### F05 — Création de transactions locales

**Description**
Saisie manuelle de transactions par les utilisateurs, indépendamment de tout import bancaire. Une transaction locale peut représenter une dépense espèces, un futur prélèvement non encore effectué, ou un mouvement entre comptes.

**User stories**

- En tant qu'utilisateur, je veux saisir rapidement une dépense espèces depuis mon mobile, même offline.
- En tant qu'utilisateur, je veux planifier une dépense future (ex. cadeau d'anniversaire dans 3 semaines) pour qu'elle apparaisse dans mon solde prévisionnel.
- En tant qu'utilisateur, je veux saisir un transfert entre deux de mes comptes (virement vers épargne) en une seule opération.

**Règles métier**

- Une transaction a : `date`, `amount` (centimes, signé), `currency`, `account_id`, `payee`, `description`, `category_id`, `splits[]`, `attachments[]`, `tags[]`, `created_by`, `state`.
- États : `draft`, `planned` (date future), `confirmed`, `void`.
- Modèle de double-entrée : toute transaction se compose de `splits` dont la somme égale zéro.
- Transferts inter-comptes : transaction unique avec deux splits sur deux comptes différents.
- Devises multiples : pas d'opération directe cross-devise (refus au niveau du value object `Money`), conversion explicite via une transaction dédiée.
- Création offline-first : SQLite local, sync via PowerSync à la reconnexion.

**Dépendances** : F02.

---

### F06 — Transactions récurrentes

**Description**
Définition de transactions qui se répètent automatiquement (loyer, abonnements, salaire), avec génération anticipée pour alimenter le solde prévisionnel.

**User stories**

- En tant qu'utilisateur, je veux déclarer mon loyer comme transaction mensuelle automatique, à date fixe.
- En tant qu'utilisateur, je veux suspendre temporairement une récurrence (ex. abonnement en pause).
- En tant qu'utilisateur, je veux modifier une seule occurrence d'une récurrence sans affecter les suivantes.
- En tant qu'utilisateur, je veux modifier une règle (changer le montant du loyer) et que ça n'affecte que les occurrences futures non encore générées.

**Règles métier**

- Modèle : `recurring_rule` (cadence : daily, weekly, monthly, yearly, ou cron-like) + `start_date` + `end_date` (nullable) + `template` (transaction modèle).
- Génération des occurrences : un job génère les occurrences futures jusqu'à fin du mois en cours en état `planned`.
- Exception sur une occurrence : duplique en `confirmed` modifiable sans toucher au modèle.
- Suspension : flag `paused_until` qui empêche la génération sans supprimer la règle.
- **Modification d'une règle de récurrence** : s'applique **uniquement aux occurrences futures non encore générées**. Les occurrences `planned` déjà générées restent inchangées (l'utilisateur peut les éditer une par une si besoin). Les occurrences `confirmed` ne sont jamais modifiées rétroactivement.
- Versioning de la règle : conservation de l'historique des modifications (audit trail) pour traçabilité.
- À la confirmation d'une occurrence (manuellement ou par pointage bancaire), l'état passe à `confirmed` et alimente le solde réel.

**Dépendances** : F05, F11.

---

### F07 — Pointage transactions locales ↔ bancaires

**Description**
Réconciliation entre les transactions locales saisies par l'utilisateur (ou générées par récurrence) et les transactions effectivement remontées par la banque. Étape clé pour vérifier que la réalité bancaire correspond à la projection.

**User stories**

- En tant qu'utilisateur, je veux que l'app me suggère automatiquement le pointage d'une transaction bancaire avec une transaction locale similaire.
- En tant qu'utilisateur, je veux pouvoir confirmer ou rejeter manuellement chaque suggestion.
- En tant qu'utilisateur, je veux savoir quelles transactions bancaires n'ont pas encore été rapprochées (ex. un prélèvement inattendu).
- En tant qu'utilisateur, je veux dépointer une transaction si je me suis trompé.

**Règles métier**

- Algorithme de suggestion : matching par `date ± 3 jours`, `montant exact`, libellé fuzzy (Levenshtein < seuil).
- États d'une transaction bancaire : `unmatched`, `suggested` (lié à un candidat local), `matched`, `ignored`.
- Une transaction bancaire peut être marquée "ignorée" (frais bancaires non saisis localement).
- Une transaction locale matchée prend le statut `confirmed` et "absorbe" l'ID bancaire (ou inversement).
- Audit trail : qui a pointé quoi, quand, possibilité de dépointer.
- Détection des duplicates : transaction bancaire qui correspond à plusieurs candidats → l'utilisateur tranche.

**Dépendances** : F04, F05, F06.

---

### F08 — Gestion de budgets

**Description**
Définition de catégories de dépenses (hiérarchie arborescente illimitée) avec montant alloué par période, suivi de la consommation, alertes de dépassement.

**User stories**

- En tant qu'utilisateur, je veux définir un budget "Courses" de 400€/mois pour le foyer.
- En tant qu'utilisateur, je veux organiser mes catégories en hiérarchie aussi profonde que nécessaire (Loisirs > Sortie > Restaurant > Restaurant gastronomique).
- En tant qu'utilisateur, je veux voir en temps réel le pourcentage consommé de chaque budget.
- En tant qu'utilisateur, je veux être alerté quand un budget atteint 80% / 100%.
- En tant que couple, nous voulons des budgets séparés par utilisateur ou partagés.

**Règles métier**

- Une catégorie a : `name`, `color`, `icon`, `parent_id` (hiérarchie **illimitée en profondeur**).
- Un budget = `category_id` + `period` (mensuel par défaut) + `amount` + `scope` (perso / commun) + `users[]` (qui contribue).
- Calcul de la consommation : somme des splits sur les transactions confirmées de la période, filtrées par `category_id` (incluant les sous-catégories) et `scope`.
- Report optionnel du reliquat d'un mois sur l'autre (configurable par budget).
- Agrégation hiérarchique : un budget posé sur une catégorie parent agrège automatiquement les dépenses de ses enfants.
- Lien direct avec F10 : une transaction "non-budgétisée" est une transaction confirmée dont la catégorie (ou ses ancêtres) n'a pas de budget actif couvrant le montant.

**Dépendances** : F05.

---

### F09 — Dettes entre utilisateurs

**Description**
Suivi des créances/dettes entre les utilisateurs du foyer, alimentées par les transactions effectuées sur les comptes communs et par les dépenses non-budgétisées. Quote-part par défaut configurable au niveau du compte, **ajustable individuellement par dette**.

**User stories**

- En tant que membre d'un compte commun, je veux savoir combien je dois à mon conjoint à tout moment.
- En tant qu'utilisateur, je veux que les dettes soient générées par défaut selon la quote-part configurée sur le compte (50/50 par défaut).
- En tant qu'utilisateur, je veux pouvoir **ajuster la quote-part d'une dette précise** après sa création (ex. "cette dépense, c'est 80% pour moi car c'est mon cadeau d'anniversaire").
- En tant qu'utilisateur, je veux marquer une dette comme remboursée (par virement réel ou par compensation comptable).
- En tant qu'utilisateur, je veux voir l'historique des règlements de dettes.
- En tant qu'utilisateur, je veux savoir d'où vient chaque dette (quelle(s) transaction(s) l'ont générée).

**Règles métier**

- Une dette est un montant signé orienté : `from_user_id → to_user_id`, `amount`, `account_id`, `source_transaction_id`, `share_ratio` (la part appliquée à cette dette précise).
- **Invariant zero-sum** : la somme algébrique des dettes générées par une transaction = 0.
- Génération automatique selon la quote-part par défaut du compte (cf. F02) :
  - Compte commun 50/50, dépense de 100€ payée depuis le compte commun : pas de dette générée (le compte commun absorbe).
  - Dépense personnelle de U1 de 100€ avec contribution prévue 50/50 → U2 doit 50€ à U1.
- **Ajustement de quote-part par dette** : l'utilisateur peut modifier la `share_ratio` d'une dette existante. Le recalcul est immédiat et l'invariant zero-sum est maintenu (l'ajustement bascule la différence entre les utilisateurs concernés). L'historique de la valeur précédente est conservé.
- Règlement d'une dette : transaction spéciale "settlement" qui annule la dette (réelle = virement, ou virtuelle = compensation).
- Possibilité de "netter" plusieurs dettes en un seul règlement.
- Audit trail : historique des modifications de quote-part avec auteur et timestamp.

**Dépendances** : F02 (quote-parts par défaut), F05, F10.

---

### F10 — Transactions non-budgétisées → dettes

**Description**
Cas particulier de la gestion des dettes : quand une transaction sur un compte commun excède le budget de sa catégorie, **l'excédent** (montant au-delà du budget restant) est imputé en dette personnelle au créateur de la transaction. Le montant couvert par le budget reste dans la logique normale du compte commun.

**User stories**

- En tant qu'utilisateur, je veux qu'un achat partiellement couvert par le budget génère une dette uniquement sur la part excédentaire.
- En tant qu'utilisateur, je veux pouvoir reclasser après coup une transaction "non-budgétisée" en transaction normale si je me trompe (en augmentant le budget par exemple).
- En tant qu'utilisateur, je veux voir une liste dédiée des transactions ayant généré des dettes par dépassement de budget.

**Règles métier — Calcul du montant générant une dette**

Pour une transaction `T` de montant `M` sur compte commun avec catégorie `C` :

1. Soit `B` = budget actif sur `C` (ou un ancêtre) pour la période de `T`.
2. Soit `R` = budget restant avant cette transaction = `B.amount - consommation_avant_T`.
3. Soit `E` = excédent généré par `T` = `max(0, M - R)`.
4. **Le montant `E` génère une dette**, le montant `M - E` reste dans la logique normale du compte commun.

**Exemples concrets**

- Budget Courses 400€/mois, déjà consommé 350€. Transaction de 100€ par U1 sur compte commun 50/50.
  - Budget restant `R = 50€`.
  - Excédent `E = 100 - 50 = 50€`.
  - Logique normale : 50€ absorbés par le compte commun (aucune dette).
  - Logique non-budgétisée : 50€ génèrent une dette → U2 doit 25€ à U1 (50€ × 50%).
- Transaction de 30€ sur la même catégorie alors que budget restant = 50€ : excédent nul, aucune dette générée.
- Transaction de 100€ sur une catégorie sans budget : excédent = 100€, dette de 50€ générée intégralement.

**Effets**

- L'utilisateur peut explicitement marquer une transaction "hors budget" — dans ce cas la totalité du montant génère des dettes, indépendamment du budget.
- Reclassement possible a posteriori : si l'utilisateur ajoute un budget couvrant la dépense ou augmente un budget existant, les dettes générées sont automatiquement réévaluées (recalcul, pas suppression d'historique, audit trail conservé).
- Liste filtrée disponible dans le dashboard ("Transactions ayant généré des dettes").

**Dépendances** : F08, F09.

---

### F11 — Dashboard multi-soldes

**Description**
Vue principale présentant l'état financier de l'utilisateur connecté : ses comptes, ses soldes selon plusieurs angles (réel, prévisionnel, projeté), ses dettes, l'état des budgets en cours.

**User stories**

- En tant qu'utilisateur, je veux voir sur ma page d'accueil tous mes comptes avec leur solde réel.
- En tant qu'utilisateur, je veux voir mon solde prévisionnel (incluant les transactions planifiées à court terme).
- En tant qu'utilisateur, je veux voir mon solde projeté à fin de mois (incluant les récurrences générées).
- En tant qu'utilisateur, je veux un graphique de l'évolution de mes soldes sur les 12 derniers mois.
- En tant qu'utilisateur, je veux voir mes dettes nettes par contrepartie.

**Règles métier**

- **Solde réel** : somme des splits des transactions `confirmed` sur le compte, jusqu'à aujourd'hui.
- **Solde prévisionnel** : solde réel + transactions `planned` jusqu'à `today + 7 jours`.
- **Solde projeté** : solde réel + toutes les transactions `planned` jusqu'à **fin du mois en cours** (horizon fixe).
- Dashboard filtré par utilisateur connecté : ne montre que ses comptes personnels et les comptes communs dont il est membre.
- Widgets configurables (priorité V1) : soldes, dettes, budgets, top dépenses du mois, objectifs d'épargne.
- Calculs faits côté client (SQLite local) pour réactivité offline-first.

**Dépendances** : F02, F05, F06, F09.

---

### F12 — Épargne avec objectifs et prévision

**Description**
Définition d'objectifs d'épargne avec montant cible, échéance, projection d'atteinte basée sur le rythme d'abondement.

**User stories**

- En tant qu'utilisateur, je veux définir un objectif "Achat voiture" : 8 000€ d'ici 18 mois.
- En tant qu'utilisateur, je veux lier un objectif à un compte d'épargne dédié pour suivre les versements.
- En tant qu'utilisateur, je veux voir si je suis en avance ou en retard sur mon objectif.
- En tant qu'utilisateur, je veux être notifié quand un objectif est atteint.

**Règles métier**

- Un objectif a : `name`, `target_amount`, `target_date`, `account_id` (optionnel), `monthly_contribution_target` (optionnel).
- Projection : taux de remplissage actuel + extrapolation au rythme moyen des 3 derniers mois.
- État d'avancement : en retard / dans les temps / en avance.
- Un compte peut héberger plusieurs objectifs (split virtuel du solde).
- Versement = transaction normale liée à l'objectif (via tag ou catégorie dédiée).

**Dépendances** : F02, F05, F13.

---

### F13 — Notifications multi-canal

**Description**
Système de notifications permettant d'alerter l'utilisateur sur événements importants via plusieurs canaux : email, push mobile, in-app. Inclut le canal temps réel web via **Server-Sent Events (SSE)** pour la synchronisation des badges et compteurs lorsque l'app est ouverte dans un onglet.

**User stories**

- En tant qu'utilisateur, je veux recevoir un email quand mon consentement bancaire expire dans 7 jours.
- En tant qu'utilisateur, je veux une notification push quand une transaction inattendue dépasse 200€.
- En tant qu'utilisateur, je veux voir un badge in-app sur les transactions à pointer.
- En tant qu'utilisateur, je veux confirmer ou rejeter via notification push une action MCP en attente (cf. F14).
- En tant qu'utilisateur, je veux que le badge "actions en attente" apparaisse instantanément sur ma web app ouverte, sans rafraîchissement manuel, dès que Claude propose une action depuis un autre onglet ou un autre device.
- En tant qu'utilisateur, je veux configurer quels événements me notifient et sur quel canal.

**Règles métier**

- Canaux : email (SMTP), push (notifications mobile via Capacitor), in-app (badge + centre de notifications), **temps réel web via Server-Sent Events (SSE)** pour synchronisation immédiate des sessions ouvertes.
- Choix SSE plutôt que WebSocket : protocole unidirectionnel suffisant (serveur → client) pour notre besoin de push d'événements, plus simple à opérer, compatible avec les reverse proxies HTTP/1.1 + HTTP/2 standards et avec Cloudflare. Reconnexion automatique côté navigateur incluse dans le protocole.
- Types d'événements notifiables (V1) :
  - Expiration imminente de consentement Enable Banking (J-7)
  - Échec d'import bancaire (J)
  - Budget dépassé (seuils 80% / 100% / 120%)
  - Nouvelle dette générée
  - Objectif d'épargne atteint
  - Transaction inattendue (montant > seuil configurable)
  - **Action MCP en attente de confirmation** (push immédiat sans contenu sensible — cf. F14)
  - **Digest d'actions MCP non traitées depuis plus de 6h** (email, sans lien d'action direct)
  - **PAT compromis détecté et désactivé** (push + email, non désactivables)
  - **Alerte PAT probabiliste** (push avec bouton "Désactiver maintenant", canal non désactivable pour la sécurité)
- Préférences utilisateur : matrice `event_type × channel` activable/désactivable, sauf pour les événements de sécurité (compromission ou alerte PAT) qui restent toujours actifs.
- Regroupement des notifications similaires en digest si plus de N en 1h.
- **Contenu push sécurisé** : aucune notification push ne contient de montant, libellé de compte, ou identifiant sensible — pour ne pas leaker sur lock screen. Tap → ouvre l'app authentifiée à l'écran concerné.

**Dépendances** : transverse au système.

---

### F14 — Accès MCP pour Claude

**Description**
Exposition de l'application comme **MCP server** pour permettre à Claude (Claude Code en local, Claude.ai en remote, ou agents n8n via Claude API) d'interagir avec les données financières du foyer : analyse de patterns, suggestions de budgets, recherche assistée, et à terme création/modification avec confirmation humaine.

**Principe directeur**
L'agent est un **assistant**, pas un automate. Toutes les actions à effet (création, modification, suppression) sont soumises à confirmation humaine explicite. La lecture est libre, l'écriture est gated.

**User stories**

*Lecture (V1)*

- En tant qu'utilisateur, je veux demander à Claude "analyse mes dépenses de courses sur les 6 derniers mois" et qu'il interroge mes données pour produire une analyse pertinente.
- En tant qu'utilisateur, je veux que Claude détecte les transactions inhabituelles dans mon historique.
- En tant qu'utilisateur, je veux que Claude m'aide à comprendre pourquoi mon solde a baissé ce mois-ci.
- En tant qu'utilisateur, je veux que Claude propose un budget basé sur mon historique réel.
- En tant qu'utilisateur, je veux que Claude ait accès uniquement à mes données (pas celles des autres membres du foyer, même si je suis admin).

*Écriture avec confirmation (V2)*

- En tant qu'utilisateur, je veux dire à Claude "crée une transaction récurrente de 50€ pour Netflix le 5 de chaque mois" et qu'il prépare la création, mais que je doive valider via push notification avant que ce soit effectif.
- En tant qu'utilisateur, je veux que Claude crée plusieurs budgets en lot après ses recommandations, validés en un seul clic.
- En tant qu'utilisateur, je veux voir clairement quel agent a proposé l'action (nom du PAT, transport, IP si applicable) avant de valider.
- En tant qu'utilisateur, je veux pouvoir modifier une action proposée par Claude avant de la confirmer (cas où il est proche mais pas exact).
- En tant qu'utilisateur, je veux que la proposition originale de Claude reste consultable même après que je l'ai modifiée et confirmée.

**Règles métier**

*Authentification et autorisation*

- Accès via **Personal Access Token** (PAT) généré dans l'app par l'utilisateur (cf. F01).
- Un PAT est strictement lié à un utilisateur et **hérite de ses droits**, jamais plus (un admin ne peut pas générer un PAT "admin" qui voit toutes les données du foyer).
- Scope V1 : `read_only` ou `read_write` au niveau du PAT entier. Granularité fine par tool prévue post-V1.
- Révocation immédiate possible depuis l'app. Auto-désactivation en cas de comportement suspect (cf. F01).

*Transports*

- **stdio** : pour Claude Code local. Le MCP server est lancé en process par Claude Code.
- **Streamable HTTP** (norme MCP 2025+) : pour Claude.ai, n8n, et agents distants. Exposé via Cloudflare Tunnel + Access (même chaîne que l'API FastAPI).

*Tools disponibles*

V1 — Lecture seule (MVP de la feature) :

| Tool | Description |
|---|---|
| `list_accounts` | Liste des comptes accessibles à l'utilisateur du PAT |
| `get_account` | Détails d'un compte (solde, type, propriétaires) |
| `list_transactions` | Recherche de transactions avec filtres (compte, date, catégorie, montant, texte) |
| `get_transaction` | Détails d'une transaction (splits, audit) |
| `get_balance` | Solde réel / prévisionnel / projeté à une date |
| `list_budgets` | Budgets de l'utilisateur avec consommation actuelle |
| `list_debts` | Dettes en cours par contrepartie |
| `list_savings_goals` | Objectifs d'épargne et avancement |
| `analyze_spending` | Agrégation par catégorie sur une période |
| `find_recurring_charges` | Détection automatique de récurrences potentielles dans l'historique |
| `summary` | Vue consolidée (équivalent dashboard) |

V2 — Écriture avec confirmation :

| Tool | Description |
|---|---|
| `propose_transaction` | Prépare une transaction, génère un `confirmation_id`, déclenche une notification push. Effective seulement après confirmation. |
| `propose_budget` | Prépare un (ou plusieurs) budget(s), confirmation requise. |
| `propose_recurring_rule` | Prépare une règle de récurrence, confirmation requise. |
| `propose_savings_goal` | Prépare un objectif, confirmation requise. |
| `get_action_status` | Récupère l'état d'une action proposée (`pending`, `confirmed`, `rejected`, `expired`, `superseded`). |
| `confirm_pending_action` | Confirme une action en attente (appelable par l'utilisateur lui-même ou via notification — pas via PAT en V2 pour préserver la confirmation humaine). |

*Format de réponse des tools d'analyse*

Les tools de type analyse (`analyze_spending`, `find_recurring_charges`, `summary`, `find_unusual_transactions`) retournent **simultanément deux formats** :

- `data` : JSON structuré, exploitable programmatiquement (agrégats, séries temporelles, tableaux).
- `markdown` : rendu pré-formaté optimisé pour la consommation par un LLM (tableaux markdown, listes, mise en avant des chiffres clés).

Claude choisit selon le contexte : la version markdown alimente directement sa réponse à l'utilisateur, la version JSON permet des transformations ou enchaînements analytiques.

*Workflow de confirmation des actions V2*

Le workflow est conçu pour rendre l'expérience fluide tout en garantissant qu'**aucune action n'est effective sans validation humaine explicite**.

**Architecture concrète**

- **Pending actions = entité de première classe** dans l'app (web et mobile). Section dédiée accessible depuis le menu principal, avec badge compteur en temps réel.
- **Push notification immédiate** à la création d'une action proposée :
  - Message court et sans contenu sensible : "Action en attente de Claude" — pas de montant, pas de compte, pour éviter toute fuite sur lock screen.
  - Tap → ouvre l'app sur l'écran de la pending action concernée.
- **Synchronisation temps réel web via Server-Sent Events (SSE)** (cf. F13) : si l'utilisateur est sur son ordinateur en train de discuter avec Claude.ai dans un onglet, le badge apparaît instantanément sur l'app ouverte dans un onglet voisin. Pas besoin de regarder le téléphone.
- **Écran de confirmation avec preview riche** :
  - Détails complets de l'action (compte, montant, libellé, catégorie, impact sur les soldes et budgets).
  - Source : nom du PAT ayant proposé, horodatage, transport (stdio / HTTP), IP si HTTP.
  - Trois boutons :
    - **Confirmer** : l'action devient effective immédiatement.
    - **Rejeter** : l'action est marquée rejetée, Claude est informé au prochain appel.
    - **Modifier puis confirmer** : ouvre l'éditeur avec les champs pré-remplis pour ajuster avant validation (cas où Claude se rapproche du bon résultat mais pas parfaitement). Crée une nouvelle action dérivée (cf. *Modélisation : audit lineage immutable* ci-dessous).
- **Email = digest, jamais action directe** :
  - Si une action reste en attente plus de **6 heures**, un email de digest est envoyé.
  - L'email **ne contient aucun lien d'action directe** : juste "Tu as N actions en attente, ouvre l'app pour les traiter".
  - Le lien pointe vers l'app, qui exige authentification normale. Bénéfice : trace écrite et rappel, sans introduire de canal d'auth supplémentaire vulnérable.
- **Expiration automatique à 24h** : passé ce délai, l'action passe à l'état `expired`. Claude est notifié au prochain appel (si la session MCP est encore active) ou la prochaine fois qu'il interroge `get_action_status`.
- **Batch confirmation** : si Claude propose N actions en bloc (ex. création de plusieurs budgets après une analyse), elles sont groupées en un seul écran avec un bouton "Tout confirmer" et des cases individuelles décochables pour exclure certains éléments. Chaque élément a son propre lineage individuel.

**Comportement par transport**

- **stdio (Claude Code local)** : Claude répond à l'utilisateur "Action proposée (ID `xxx`), confirme-la dans ton app". L'utilisateur valide dans l'app, puis dit à Claude "fait, continue". Claude peut aussi appeler `get_action_status(id)` pour vérifier sans interruption manuelle.
- **HTTP (Claude.ai, n8n, autres agents distants)** : même logique, mais la synchronisation temps réel SSE du badge web rend l'expérience fluide si l'app est ouverte dans un onglet.

*Modélisation : audit lineage immutable*

Une `pending_action` est une **trace d'intention agentique immutable**. Le payload proposé par Claude reste lisible tel quel après confirmation, rejet ou modification — jamais réécrit en place. Cette approche sépare proprement l'intention de l'agent de l'intention humaine, donne des données longitudinales sur la qualité des propositions de Claude (taux d'acceptation sans modification, deltas, champs souvent corrigés), et garantit mécaniquement qu'un bug ne peut pas écraser silencieusement l'original.

Comportements clés :

- Lors d'un `modify_then_confirm` : la pending action originale passe à l'état terminal **`superseded`** et **une nouvelle entité dérivée est créée**, portant un FK `derived_from_action_id` vers l'originale. La nouvelle entité contient le payload modifié validé par l'utilisateur.
- Champ symétrique `superseded_by_action_id` côté originale pour permettre le suivi descendant.
- L'UI fournit un lien "voir la proposition originale" depuis chaque action dérivée pour la transparence.
- Compatible avec les batch : chaque élément d'un batch a son propre lineage individuel, pas de couplage parasite.

Schéma de référence :

```sql
pending_action (
  id uuid PK,
  pat_id uuid FK,
  user_id uuid FK,
  tool_name text,
  proposed_payload jsonb,                 -- immutable
  state text,                             -- pending | confirmed | rejected | expired | superseded
  derived_from_action_id uuid FK NULL,    -- si dérivée d'une originale (modify_then_confirm)
  superseded_by_action_id uuid FK NULL,   -- si originale supplantée
  resolved_at timestamptz NULL,
  resolved_payload jsonb NULL,            -- payload final si confirmé (= proposed_payload sauf si dérivée)
  retention_policy text NULL,             -- régime de rétention appliqué (cf. ci-dessous)
  preserve_for_incident boolean DEFAULT false,
  ...
)
```

*Rétention des pending actions*

Politique étagée combinant trois principes : **préservation des preuves d'incident**, **différenciation par outcome**, **dégradation progressive à long terme**. Paramètre **système** (non configurable par l'utilisateur en V1) pour éviter des comportements imprévisibles selon les préférences individuelles.

**Préservation pour incident (règle transverse, prioritaire)**

Si un PAT est flaggé compromis (auto-désactivation, cf. F01), toutes ses pending actions sont **préservées indéfiniment**, indépendamment de la politique normale. Implémentation : flag `preserve_for_incident` poussé sur les actions concernées au moment de la désactivation du PAT. Aucune purge ne s'applique à une action marquée ainsi — c'est de la preuve d'incident.

**Politique par outcome**

| Outcome | Visibilité standard | Action terminale |
|---|---|---|
| `confirmed` | 90 jours | Lien vers la transaction/entité créée, payload archivé |
| `rejected` | 90 jours | Purge complète |
| `expired` | 12 mois | Dégradation vers squelette d'audit |
| `superseded` (`modify_then_confirm`) | 12 mois | Dégradation, mais **conservation du delta** entre proposition originale et payload finalement confirmé (valeur forensique élevée pour comprendre où Claude se trompe systématiquement) |

**Dégradation à long terme (squelette d'audit)**

Passé l'horizon de visibilité standard, dégradation vers un **squelette d'audit** conservé indéfiniment (volume négligeable à l'échelle d'un foyer) :

- Conservés : `timestamp`, `pat_id`, `tool_name`, `outcome`, `hash` des paramètres.
- Purgés : `proposed_payload`, `resolved_payload`, libellés, montants, identifiants de comptes.

Bénéfice : permet de repérer rétroactivement des patterns de compromission (ex. "ce PAT a généré 200 actions en 1h le 12 mars") sans rétention indéfinie de données sensibles, conforme au principe de minimisation RGPD.

**Implémentation**

Deux jobs cron suffisent : dégradation à 12 mois, purge selon outcome. Le champ `retention_policy` sur la pending action assure la traçabilité du régime appliqué pour audit.

*Sécurité et observabilité*

- **Audit trail systématique** : chaque appel MCP est loggé avec `timestamp`, `pat_id`, `user_id`, `tool_name`, `parameters_hash`, `result_summary`, `duration_ms`, `ip_address` (si HTTP), `asn` (si HTTP).
- **Rate limiting par PAT** : 60 requêtes/min par défaut, configurable. Dépassement déclenche HTTP 429 et alimente les heuristiques de compromission (cf. F01).
- **Pas de données sensibles dans les paramètres** : pas de mot de passe, jamais. Les tools d'écriture ne prennent que des données métier.
- **Quotas Enable Banking préservés** : les tools MCP ne déclenchent jamais un appel synchrone à Enable Banking. Si une donnée n'est pas en cache local, l'appel attend le prochain polling.

*Granularité des tools*

- Privilégier des tools sémantiques (`analyze_spending`, `find_unusual_transactions`) plutôt que des CRUD bas-niveau qui forcent Claude à enchaîner 50 appels.
- Chaque tool retourne des données pré-agrégées et formatées pour la consommation par un LLM.

**Hors périmètre**

- Pas de tool donnant accès aux logs d'audit eux-mêmes (méta-accès interdit).
- Pas de tool de gestion des utilisateurs ou des droits (réservé à l'UI admin).
- Pas de tool de gestion des connexions bancaires (Enable Banking est une responsabilité humaine).
- Pas de modification des dettes ou règlements via MCP (trop sensible, manuel uniquement).
- Pas de tool de gestion des PAT eux-mêmes (création, révocation : UI uniquement).

**Dépendances** : F01 (PAT), F03 (autorisation), F13 (notifications push + canal SSE pour confirmations V2).

---

## 5. Hors périmètre (explicitement exclu)

- **Investissements (PEA, assurance-vie, crypto, immobilier)** : non géré dans la V1.
- **Multi-foyer sur la même instance** : un déploiement = un foyer.
- **Catégorisation automatique par IA en saisie** : catégorisation manuelle initialement (Claude via MCP peut suggérer mais l'utilisateur applique).
- **Connexion bancaire hors France** : seuls les ASPSP français supportés par Enable Banking.
- **Crédits structurés avec échéancier amortissable** : un crédit = compte de type "credit" avec transactions, sans logique d'amortissement native.
- **Multi-devise active** : EUR par défaut, multi-devise supporté au niveau du modèle mais sans conversion automatique.
- **Export comptable (FEC, autres)** : aucun export normé prévu pour la V1.
- **Actions automatiques par agent IA** : Claude ne fait jamais d'action irréversible sans confirmation humaine.

---

## 6. Phasing suggéré

### MVP — Cœur fonctionnel (cible 4-6 mois solo full-time)

> Recalibration de la cible 2-3 mois initiale après inventaire honnête (infra Podman/Quadlet/Caddy/Cloudflare/Tailscale/Restic, PowerSync setup + sync rules + write upload handler, scaffolding Capacitor/React/shadcn pour ~15 écrans, bootstrap test stack, ADRs, application des arbitrages de domaine).

1. F01 Auth (sans PAT) + F02 Comptes + F03 Droits
2. F05 Création transactions locales + F08 Budgets
3. F04 Import OFX manuel uniquement (avant Enable Banking)
4. F11 Dashboard avec solde réel uniquement
5. **F09 + F10 Dettes** :
   - **F09 MVP scope** : mécanisme `share_request` (demande de partage explicite depuis un compte personnel) + `settlement` (règlement) + vue "mes dettes par contrepartie". Aucune génération automatique depuis un compte personnel.
   - **F10 promu au MVP** : mécanique d'excédent budgétaire sur compte commun (`debt_generation_override`, calcul `E = max(0, M - R)`, matérialisation server-side via `DebtCalculator`). Promotion justifiée : sans F10, le module `debts` est conceptuellement bancal, et l'app n'est utilisable conformément au concept produit qu'avec la gestion d'overflow.

À ce stade, l'app est utilisable comme tracker manuel multi-utilisateur **avec gestion complète des dettes croisées (manuelles via share_request et automatiques via overflow F10)**.

### V1 — Automatisation et intelligence (cible +3 mois)

6. F04 Import Enable Banking (Société Générale, Banque Populaire)
7. F06 Transactions récurrentes
8. F07 Pointage local ↔ bancaire
9. F11 Soldes prévisionnel et projeté
10. F01 Personal Access Tokens (avec heuristiques Tier 1 de détection de compromission)
11. **F14 MCP server en lecture seule** (tools V1, double format JSON + markdown)
12. F12 Épargne avec objectifs
13. F13 Notifications multi-canal (email, push, in-app, **SSE** pour synchro temps réel web)
14. F01 Page "Activité de mes PAT"

### V2 — Agent et confort (cible +2 mois)

15. F14 MCP server en écriture avec confirmation (tools V2 + workflow `propose` → notification → écran de confirmation → `confirm` / `reject` / `modify_then_confirm`)
16. F14 Audit lineage immutable des pending actions + politique de rétention étagée
17. F13 Digest email des actions en attente (>6h) + expiration 24h
18. Widgets de dashboard configurables
19. Recherche full-text sur transactions
20. Tags libres
21. Pièces jointes (reçus photographiés)
22. Export CSV ad hoc

### Post-V2 — Affinements

- F01 Granularité fine du scope des PAT (par tool ou par type d'action)
- F01 Heuristiques V1.5 de détection de compromission (volume cumulé 24h, ASN inédit, PAT dormant, énumération massive) calibrées sur la baseline réelle collectée
- F14 Tools d'analyse étendus (`find_unusual_transactions`, projections multi-mois, etc.)

---

## 7. Invariants transversaux

Quel que soit le module, ces règles s'appliquent partout :

1. **Tous les montants en centimes entiers** (jamais de float pour de l'argent).
2. **Double-entrée systématique** : toute transaction a une somme de splits égale à zéro.
3. **Devise toujours explicite** : pas d'opération arithmétique entre montants de devises différentes.
4. **Idempotence des mutations API et MCP** : toute requête de mutation porte un `client_request_id` pour permettre les retries safe.
5. **Audit trail** : toute modification d'une transaction confirmée laisse une trace (qui, quand, valeur avant/après, source = UI / MCP / Import). Tous les appels MCP loggés.
6. **Offline-first** : toute saisie utilisateur fonctionne sans réseau, sync transparente via PowerSync.
7. **Server-authoritative** : en cas de conflit de sync, le serveur arbitre selon une règle métier (par défaut last-write-wins, customisable par endpoint).
8. **Confirmation humaine pour toute action irréversible via agent** : aucune action d'écriture MCP n'est effective sans validation explicite de l'utilisateur via l'app (pas via PAT, pas via email).
9. **L'admin gère les droits, pas les données** : même un admin n'accède aux transactions d'un compte que s'il en est membre. Pas de compte sans utilisateur.
10. **Push notifications sans contenu sensible** : aucun montant ni libellé n'apparaît sur lock screen — tap exigé pour révéler après auth.
11. **Immutabilité des intentions agentiques** : un `proposed_payload` d'une pending action ne peut jamais être réécrit en place. Modification = nouvelle entité dérivée avec FK vers l'originale.
12. **Alerter ≠ désactiver** : la désactivation automatique d'un PAT est réservée aux signaux binaires sans ambiguïté. Les signaux probabilistes alertent l'utilisateur qui tranche.

---

## 8. Glossaire

| Terme | Définition |
|---|---|
| **ASPSP** | Account Servicing Payment Service Provider — la banque (DSP2) |
| **AISP** | Account Information Service Provider — agrégateur (Enable Banking) |
| **DSP2** | Directive européenne sur les services de paiement |
| **SCA** | Strong Customer Authentication — authentification forte bancaire |
| **OFX** | Open Financial Exchange — format d'export bancaire standardisé |
| **MCP** | Model Context Protocol — protocole d'exposition de tools pour LLM agentique |
| **PAT** | Personal Access Token — jeton d'accès personnel, scopé par utilisateur |
| **Pending action** | Action proposée par un agent IA via MCP, en attente de confirmation humaine |
| **Audit lineage** | Chaînage immutable entre une pending action originale et ses dérivées (`modify_then_confirm`) via FK `derived_from_action_id` |
| **Squelette d'audit** | Métadonnées d'une pending action conservées après purge du payload (timestamp, pat_id, tool_name, outcome, hash) |
| **SSE** | Server-Sent Events — canal HTTP unidirectionnel serveur → client, utilisé pour la synchro temps réel du web |
| **ASN** | Autonomous System Number — identifiant d'opérateur réseau, utilisé pour la whitelist géo des détections PAT |
| **Split** | Une ligne d'une transaction (montant + compte ou catégorie cible) |
| **Pointage** | Réconciliation manuelle ou suggérée d'une transaction locale avec son équivalent bancaire |
| **Quote-part** | Ratio de propriété d'un utilisateur sur un compte commun (et par défaut, ratio appliqué aux dettes générées par ce compte) |
| **Settlement** | Transaction de règlement d'une dette entre utilisateurs |
| **Solde réel** | Somme des transactions confirmées jusqu'à aujourd'hui |
| **Solde prévisionnel** | Solde réel + transactions planifiées à court terme (J+7) |
| **Solde projeté** | Solde réel + toutes les transactions planifiées jusqu'à fin du mois en cours |

---

## 9. Décisions produit tranchées

| Question | Décision |
|---|---|
| Quote-part par défaut sur compte commun | 50/50, ajustable individuellement par dette générée |
| Calcul des dettes pour transactions partiellement hors budget | Seul l'excédent (montant − budget restant) génère une dette |
| Profondeur de la hiérarchie de catégories | Illimitée |
| Horizon du solde projeté | Fin du mois en cours (fixe) |
| Politique d'import OFX | Preview hybride conditionnel (auto si tous critères de sécurité OK, preview sinon) |
| Transactions sur compte commun par non-membre | Refusé strictement, y compris pour l'admin. L'admin gère les droits, pas les données. Pas de compte sans utilisateur. |
| Versioning des règles de récurrence | Modification appliquée uniquement aux occurrences futures non encore générées |
| Authentification MCP | Personal Access Token par utilisateur, hérite des droits de l'utilisateur, jamais plus |
| Actions d'écriture par agent IA | Toujours soumises à confirmation humaine explicite (workflow `propose` → notification → écran de confirmation → `confirm` / `reject` / `modify_then_confirm`) |
| **Workflow de confirmation MCP** | Pending action de première classe dans l'app + push immédiat sans contenu sensible + synchro temps réel web SSE + email digest après 6h sans lien d'action + expiration 24h + batch confirmation pour propositions multiples |
| **Protocole temps réel web** | **Server-Sent Events (SSE)** — unidirectionnel suffisant pour notre besoin (serveur → client), plus simple à opérer que WebSocket, reconnexion native côté navigateur, compatible reverse proxy HTTP/1.1 + HTTP/2 et Cloudflare |
| **Nombre de PAT par utilisateur** | Illimité, chacun nommé pour traçabilité |
| **Expiration par défaut des PAT** | 1 an, paramétrable librement à la création |
| **Granularité du scope des PAT** | V1 : `read_only` / `read_write` au niveau du PAT entier. Granularité fine par tool prévue post-V1 |
| **Heuristiques de détection de compromission PAT (V1)** | 4 signaux Tier 1 : plafond 60 req/min (rejet 429), hors scope ≥ 3 en 5 min (désactivation auto), concurrence géo impossible (alerte + désactivation si 2e signal), burst soutenu 15 min (alerte). Heuristiques V1.5 (volume 24h, ASN inédit, PAT dormant) activées après baseline de 1 mois. |
| **Politique de réaction aux signaux de compromission** | Alerter ≠ désactiver. Désactivation auto uniquement sur signal binaire sans ambiguïté (hors scope). Signaux probabilistes → alerte avec bouton "Désactiver maintenant" dans la notification. Compléments structurels : page "Activité de mes PAT" + Cloudflare Access devant le MCP HTTP. |
| **Format de réponse des tools MCP d'analyse** | Double format : JSON structuré (`data`) + markdown pré-formaté (`markdown`), Claude choisit selon le contexte |
| **Modélisation `modify_then_confirm`** | Audit lineage immutable : la pending action originale passe à `superseded` (état terminal), une nouvelle entité dérivée est créée avec FK `derived_from_action_id`. Préservation de l'intention agentique originale, mesure longitudinale de la qualité des propositions, robustesse aux bugs. |
| **Rétention des pending actions** | Politique étagée : préservation indéfinie pour PAT compromis (flag `preserve_for_incident`) + différenciation par outcome (`confirmed` 90j → lien, `rejected` 90j → purge, `expired` 12 mois → squelette, `superseded` 12 mois → squelette + delta préservé) + dégradation long terme vers squelette d'audit (timestamp, pat_id, tool_name, outcome, hash) conservé indéfiniment. Paramètre système, non configurable utilisateur. |

---

## 10. Points encore ouverts

Tous les points précédemment ouverts ont été tranchés (voir §9). Les questions résiduelles relèvent désormais de l'implémentation et seront arbitrées au fil du développement :

- [ ] Calibration empirique des seuils du burst soutenu (Tier 1) et des seuils V1.5 (volume 24h, etc.) sur les 2-3 premiers mois de mise en production, en mesurant le p95/p99 du débit légitime par tool.
- [ ] Maintenance de la liste de whitelist ASN/CIDR pour la détection de concurrence géographique impossible (Anthropic, OVH, Cloudflare egress, etc.) : process et fréquence de revue.
- [ ] Choix concret de la stack SSE côté serveur (intégration FastAPI + reverse proxy Cloudflare, gestion des reconnexions et heartbeats).