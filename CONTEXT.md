# Prosperity — Application Finances Personnelles

Application personnelle multi-utilisateurs (famille), auto-hébergée, qui agrège des comptes bancaires français (DSP2) et permet la saisie manuelle de transactions, la gestion de budgets, et le suivi des dettes croisées entre membres du foyer.

## Language

### Utilisateurs et droits

**Foyer** :
L'unité d'isolation. Un déploiement = un foyer. Tous les utilisateurs d'une instance partagent ce foyer. Matérialisé par une **table `household` singleton** (UUID fixe `00000000-0000-0000-0000-000000000001`, contrainte CHECK pour interdire un second foyer). Porte `base_currency` (verrou V1, cf. ADR 0008) et `initialized_at`.
_Avoid_: famille, ménage, household (en français mixte)

**Bootstrap initial** :
Création du premier admin via flow web `/setup` ouvert si et seulement si `users` est vide ; lock-after-init (toute requête `/setup` retourne 404 après initialisation). Fallback optionnel via env vars `INITIAL_ADMIN_EMAIL`/`INITIAL_ADMIN_PASSWORD_HASH` pour scénarios de restore from backup automatisés. Pas de CLI manuelle, pas d'inscription publique.

**Invitation** :
Mécanisme par lequel un admin enrôle un nouvel utilisateur dans le foyer. Token aléatoire (`secrets.token_urlsafe(32)`) hashé en DB (`sha256`, jamais en clair), durée de validité 7 jours, **pré-attribué à un email**, révocable, ré-générable (renvoyer = nouveau token sur la même row, l'ancien lien est invalidé). **Le rôle de l'invité est toujours `member`** ; promotion en `admin` = acte séparé avec audit (jamais via invitation). Table `invitations` **server-only** (consultée via API admin, pas synchronisée via PowerSync).

**Admin** :
Rôle d'un utilisateur qui gère les droits et l'enrôlement des autres utilisateurs. **N'a pas accès aux données financières** des comptes dont il n'est pas membre.
_Avoid_: superuser, owner (du foyer)

**Member** :
Rôle d'un utilisateur ordinaire du foyer. Saisit ses propres transactions, accède aux comptes dont il est membre.
_Avoid_: user (trop générique côté domaine)

**2FA (TOTP)** :
Optionnel par utilisateur en V1, via `pyotp` + 10 **recovery codes** single-use générés à l'enrollment (hashés en DB, affichés une seule fois). Login en deux étapes (`/auth/login` → `/auth/2fa-verify`) ; **2FA validée pour la durée du access token (15 min)**, pas re-challengé sur refresh.
**Step-up obligatoire** : création d'un PAT exige une re-validation 2FA (ou re-mot-de-passe si 2FA non activée). **Pas de 2FA par défaut sur `confirm_pending_action`** ; opt-in par PAT via flag `require_2fa_on_confirm` (réservé aux users 2FA-enrolled).
**Reset** : self-service via recovery code, sinon **accès physique machine requis** (SQL manuel documenté dans runbook). Pas de reset admin-via-app : l'admin ne voit aucune donnée user (F03) — lui donner le pouvoir de reset le 2FA d'un autre user = vecteur de takeover silencieux. Cf. ADR 0013.

### Comptes

**Compte personnel** :
Compte financier avec un seul propriétaire (`owner_id`). Étanchéité dure : seul le propriétaire voit son existence détaillée, ses transactions, ses soldes. **L'admin lui-même n'y a pas accès aux données.**
_Avoid_: compte privé, compte individuel

**Compte commun** :
Compte financier avec ≥ 2 membres (table `account_members`) et une `default_share_ratio` par membre (par défaut 50/50 à 2 membres). Visibilité partagée entre membres uniquement.
_Avoid_: compte partagé, compte joint

**Quote-part** :
Ratio de propriété d'un membre sur un compte commun. Sert de défaut pour la `share_ratio` des dettes générées par ce compte. Modifiable par dette individuelle.
_Avoid_: part, ratio, share (seul)

### Transactions

**Transaction** :
Mouvement financier daté, attaché à un compte, composé de **splits** dont la somme égale zéro (double-entrée). États : `draft`, `planned`, `confirmed`, `void`.
**Aggregate root immutable à `confirmed`** : après confirmation, les splits et le montant sont **gelés** ; toute correction passe par `void` + création d'une nouvelle transaction. Seuls quelques champs restent éditables après `confirmed` : `category_id`, `tags`, `description`, `debt_generation_override`, ajout/retrait de `share_request`. Cette immutabilité garantit la double-entrée sous le modèle offline-first server-authoritative (cf. ADR 0001).
_Avoid_: opération, mouvement, écriture

**Split** :
Une ligne d'une transaction (montant signé sur un compte ou une catégorie cible). Une transaction est une collection de splits zero-sum.
**Persistance** : table relationnelle `splits` séparée (FK CASCADE vers `transactions`, index sur `transaction_id`, `account_id`, `category_id`) pour servir les agrégations analytiques (`analyze_spending`, `summary`, agrégation budget). Discipline d'aggregate maintenue : **aucune mutation directe** de `splits` cross-module ; seules les fonctions du module `transactions` écrivent dans la table. PowerSync sync atomique des deux tables sur le même bucket (`account_id`). Modèle Pydantic domaine = `Transaction(splits=[...])`.
_Avoid_: ligne, poste, entry

**Money** :
Value object `(amount_cents: int, currency: ISO4217)`. Pas d'opération arithmétique cross-devise (refus au niveau du type). Le **modèle reste multi-devise** ; l'usage fonctionnel est verrouillé à EUR en V1 via `household.base_currency` (cf. ADR 0008).
_Avoid_: amount seul, prix

**`household.base_currency`** :
Champ unique du foyer (V1 : valeur fixe EUR) qui contraint la devise de tout nouveau compte créé. Validation à `accounts.create()`. Levier d'ouverture post-V1 du multi-devise sans migration de données : supprimer le verrou + adapter les écrans agrégateurs.

**Pointage** :
Réconciliation (suggérée puis confirmée) d'une transaction locale avec son équivalent bancaire importé. Matérialisé par une entité **`Reconciliation`** distincte de la transaction (cf. ADR 0006), pas par un champ `bank_transaction_id` sur la transaction. La transaction locale conserve sa state machine indépendante ; le pointage déclenche la transition `planned → confirmed` mais n'écrit aucun champ supplémentaire sur la transaction.
_Avoid_: matching, rapprochement, reconciliation (en français mixte)

**`Reconciliation`** :
Entité du module `reconciliation` qui lie une transaction locale et une transaction bancaire. State machine indépendante : `suggested → confirmed | rejected` puis `confirmed → depointed`. Le **dépointage ne ramène jamais** la transaction locale à `planned` (cohérent avec l'aggregate immutable, ADR 0001) — pour annuler une confirmation faite par erreur via pointage, l'utilisateur doit explicitement `void` la transaction locale et en créer une nouvelle. Suggestions multiples = plusieurs `Reconciliation` à l'état `suggested` partageant le même `bank_transaction_id` ; confirmer l'une marque les autres `rejected`.

**`MatchScorer`** :
Fonction pure du `domain.py` du module `reconciliation` calculant un `match_score` 0-100 composé sur 3 signaux V1 : proximité de date (pénalité `α × delta_jours`), score libellé via **rapidfuzz token-set ratio ≥ 70 après normalisation** (strip + lowercase + retrait des préfixes bancaires standard `PRLV SEPA`, `CB`, `VIR`, `PAIEMENT`, dates ISO), **montant strict en V1** (tolérance 0 centime). Score persisté en DB pour debug et calibration future ; **non exposé à l'utilisateur en V1** (juste tri décroissant des suggestions). **Pas d'auto-confirm** : user-in-the-loop strict en V1 quel que soit le score. Trigger du matching : à chaque import (OFX ou Enable Banking) + à la demande manuelle utilisateur ; pas de batch nightly. Exclusion automatique des paires `(local_tx, bank_tx)` déjà en `Reconciliation.state ∈ {confirmed, suggested}`.

### Dettes

**Dette** :
Montant orienté `from_user_id → to_user_id` créé par une transaction d'origine. Porte une `share_ratio` ajustable individuellement. Invariant zero-sum sur l'ensemble des dettes générées par une même transaction d'origine. **Projection serveur** : la table `debts` est matérialisée par le module `debts` à chaque write de transaction et exposée en **lecture seule côté client** via les sync rules PowerSync (cf. ADR 0002). Leviers d'écriture utilisateur strictement limités à :
- `PATCH /debts/{id}/share_ratio` (scalaire LWW-safe sur la dette).
- `debt_generation_override` posé sur la transaction source.
- création d'un `settlement` (transaction normale qui annule une ou plusieurs dettes).

Le `domain.py` du module `debts` expose un `DebtCalculator` (fonction pure `(Transaction, Budget, Account) → list[Debt]`), pas un repository éditable.
_Avoid_: créance, IOU, balance entre users

**Origine d'une dette** :
Deux origines distinctes et mutuellement exclusives :
- `shared_account_overflow` : dépense sur compte commun dont l'excédent au-delà du budget restant alimente une dette (cf. F10).
- `personal_share_request` : dépense sur compte personnel pour laquelle le propriétaire a explicitement créé une **demande de partage** (cf. ci-dessous).

Un compte personnel ne génère **jamais** de dette implicitement, même si la catégorie est partagée.

**Demande de partage** (`share_request`) :
Acte explicite par lequel le propriétaire d'un compte personnel matérialise une dette envers un autre membre. Crée une dette d'origine `personal_share_request` avec un **libellé court** rédigé par le demandeur (le seul texte qu'U2 verra).
_Avoid_: split request, ask for refund, share

**Visibilité d'une dette personal_share_request** :
Le débiteur (U2) voit la dette (`from`, `to`, `amount`, `category`, `date`, `requested_by`, `libellé court`) mais **jamais** la `source_transaction_id` ni la transaction source. Cette dernière reste strictement visible par le propriétaire du compte personnel.

**`Settlement`** :
Entité du module `debts` qui matérialise un règlement d'une ou plusieurs dettes. Trois `type` distincts : `internal_transfer` (virement entre deux comptes du foyer, lié à une `Transaction` normale via `linked_transaction_id`), `external_transfer` (virement vers une contrepartie hors-foyer, lié à la transaction sortante du compte source), `virtual` (compensation comptable sans mouvement d'argent, `linked_transaction_id` NULL). Une `Settlement` porte N `SettlementLine` qui distribuent l'apurement sur des dettes (multi-debt par règlement natif, supporte nettage croisé bidirectionnel). Sync sur les buckets `user_debt_{user_id}` (mêmes que `debts`).
_Avoid_: remboursement, paiement, règlement (en français mixte)

**`SettlementLine`** :
Ligne d'un `Settlement` qui apure une portion (`amount_cents` strictement positif ; le sens du nettage est porté par l'orientation de la `Debt`, pas par un signe sur la ligne — décision D-SIGN, ADR 0011) d'une `Debt` donnée. **Solde restant d'une dette = `debt.amount_cents - sum(settlement_lines.amount_cents)`** : pas d'état sur `Debt`, le statut "réglée / partielle / ouverte" se déduit du calcul. Compatible avec ADR 0002 (Debt projection read-only).

### Budgets

**Catégorie** :
Nœud d'une hiérarchie arborescente illimitée en profondeur. Porte `name`, `color`, `icon`, `parent_id`, `archived_at`. Synchronisée au foyer (bucket `household`).
**Cycle prevention** : validation au service (walk-up des ancêtres à la création/édition de `parent_id`, `CategoryCycleError` si auto-référence directe ou indirecte). Pas de CHECK SQL.
**Suppression** : hard-delete interdit si la catégorie a des transactions ou sous-catégories ; on **archive** via `archived_at` à la place. Catégorie archivée = invisible dans les pickers, restée dans les agrégats historiques. Pas de cascade, pas de re-parentage automatique. Désarchivage libre.
**Réorganisation** (déplacer un sous-arbre via `parent_id`) : **libre**, les agrégats des transactions historiques **suivent** mécaniquement (les budgets agrègent à la lecture, pas à l'écriture). Audit log de l'opération.
_Avoid_: tag, label (les tags libres existent en plus, distincts)

**`splits.category_id NULL`** :
Autorisé dans deux cas légitimes : (1) splits de transfert inter-comptes (pas de dépense), (2) splits saisis "à la volée" en état `draft`. **Pour passer une transaction en `confirmed`, tout split *de classification* (`leg_role == "classification"`) doit avoir une `category_id`** (validé au service, ADR 0017) ; la jambe `funding` (mouvement de compte) peut rester NULL et reste exclue de la consommation budget. Pas de catégorie "Sans catégorie" magique — l'utilisateur doit choisir explicitement.

**Budget** :
Montant alloué à une catégorie sur une période (mensuel par défaut), avec scope (perso/commun) et liste de contributeurs. Agrège automatiquement les dépenses des sous-catégories.
_Avoid_: enveloppe, plafond

**Excédent budgétaire** (E) :
Pour une transaction T de montant M sur compte commun, catégorie C, budget B avec restant R : `E = max(0, M - R)`. C'est ce montant E (et seulement lui) qui alimente la logique non-budgétisée → dette (cf. F10) — **sauf override explicite via `debt_generation_override`** (cf. ci-dessous).
**Cas sans budget actif** : si **aucun budget** ne couvre la catégorie C, il n'y a pas de restant R, donc la formule `E = max(0, M − R)` ci-dessus ne s'applique pas (elle présuppose un budget). Par **convention d'extension**, la base de la dette est alors le **montant entier** (`base = M`), équivalent à `force_full_debt`. Une dépense `default` sur compte commun **non budgétée** génère donc une dette de quote-part sur tout le montant ; ajouter un budget couvrant après coup re-matérialise la dette à la baisse (cf. F10 reclassement, S11.4).
**Résolution du budget couvrant (B)** : quand plusieurs budgets actifs couvrent C (un budget sur C *et* un sur une catégorie ancêtre), B est le **plus spécifique** = catégorie la plus proche de C en descendant l'arbre (distance minimale C → catégorie du budget), tie-break déterministe `(created_at, id)`. Un budget de scope **perso** ne s'applique **jamais** à une dépense de compte commun (un compte commun n'est pas dans les comptes éligibles d'un budget perso). V1 mono-catégorie (forme canonique de dépense) ⇒ non ambigu.
**Restant R et conservation multi-transactions** : R est calculé sur les seules transactions **strictement antérieures** à T dans l'ordre total `(date, id)`, et **borné à ≥ 0** (`R = max(0, montant du budget − consommation des tx où (date, id) < (date_T, id_T))` — le clamp évite qu'une tx tardive porte une dette supérieure à son propre montant une fois le budget déjà dépassé). L'excédent est ainsi **additif et conservatif** : `Σ E = max(0, ΣM_default − budget)` sur une période (somme restreinte aux tx `default` — les tx `force_full_debt` sont exclues du compteur de consommation **et** génèrent une dette pleine à part, cf. §`debt_generation_override`) — deux dépenses `default` qui se partagent un même dépassement ne le génèrent pas chacune en double. L'ordre `(date, id)` est figé (agrégat immuable, ADR 0001) ⇒ matérialisation déterministe et idempotente, indépendante de l'ordre de confirmation. **Reclassement F10 (S11.4)** : créer, modifier (montant) ou archiver un budget re-matérialise l'overflow de **toutes** les transactions passées qu'il couvre (recalcul, pas une suppression d'historique — les `share_request` restent intacts), via le même chemin idempotent ; et éditer la `category_id` d'une tx `confirmed` re-matérialise son overflow sur le budget couvrant la nouvelle catégorie (ou le retire si elle n'est pas budgétée) **et** re-matérialise ses **voisines de période** (ancien & nouveau budget) dont le restant ordonné est décalé. La `category_id` éditée se propage à la jambe `classification` (source de vérité consommation/overflow, ADR 0001 note S11.4). _Limite V1.5 (différée)_ : le balayage de re-matérialisation n'est **pas borné dans le temps** (il parcourt tout l'historique du budget) — le coût est acquitté par une trace d'audit `debts_recomputed_on_budget_event` (compteur, sans PII) ; le retrait d'un contributeur, qui rétrécit l'éligibilité, laisse périmé l'overflow des tx du compte devenu inéligible jusqu'à leur propre re-matérialisation (hors AC).

**`debt_generation_override`** :
Levier porté par une transaction sur compte commun pour forcer la mécanique de génération de dette. Valeurs :
- `default` : règle F10 standard (seul l'excédent E alimente une dette, selon quote-part par défaut). Sans budget actif sur la catégorie, `base = M` (cf. §Excédent budgétaire).
- `force_full_debt` : la **totalité** du montant génère une dette, et la transaction est **exclue du compteur de consommation du budget** (n'alimente donc pas les alertes 80%/100%). Sémantique de "hors budget".
- `force_no_debt` : aucune dette générée, même en dépassement budgétaire. Le compte commun absorbe intégralement. Le budget reste comptabilisé normalement (et déclenche ses alertes).

Le cas "cadeau payé via compte commun, à imputer à 100% à un seul membre" s'obtient par `force_full_debt` + override individuel de `share_ratio` à 100%. Pas de primitive dédiée.

### Épargne

**`SavingsGoal`** :
Objectif d'épargne avec `name`, `target_amount`, `target_date`, `monthly_contribution_target` (optionnel). Adossé à zéro, un, ou plusieurs comptes via `savings_goal_allocations`.

**`savings_goal_allocations`** :
Table qui matérialise la répartition d'un objectif sur N comptes (`(goal_id, account_id, allocated_cents)` avec unique index sur la paire). Pas de "solde libre" matérialisé : `account.balance - sum(allocations)` à la lecture. **Auto-cap UI proportionnel** sur sur-allocation (`min(allocated, real_balance × allocated/total_allocated)`), warning UI mais pas d'erreur bloquante.

**`split.savings_goal_id`** :
FK nullable sur les splits qui exprime "ce split contribue à cet objectif" (versement épargne). Pas de surcharge tag/catégorie. Index pour agrégats rapides.

**Projection épargne** :
Calcul `ProjectionCalculator` du module `savings`. Rythme moyen sur **90j glissants**. **Historique < 30j** : projection masquée. **30j ≤ historique < 90j** : projection avec badge "estimation provisoire". **historique ≥ 90j** : projection nominale. `monthly_contribution_target` sert (i) de comparaison ("rythme observé vs cible"), (ii) de **fallback de projection** si historique vide. États : `en_avance` (>105%), `dans_les_temps` (95-105%), `en_retard` (<95%).

### Récurrences

**Règle de récurrence** (`recurring_rule`) :
Template d'une transaction qui se répète selon une cadence. Source des **occurrences** générées en `planned`. Modifications de la règle s'appliquent **uniquement aux occurrences futures non encore générées** (cf. ADR 0007).

**Occurrence** :
Transaction matérialisée à partir d'une règle de récurrence, identifiée de manière unique par `(recurring_rule_id, occurrence_date)`. Vit dans la table `transactions` comme une transaction normale (état `planned` puis `confirmed` à la confirmation). Une fois matérialisée, devient un snapshot autonome — modifier la règle ne la touche plus.

**Horizon de matérialisation** :
Fenêtre temporelle dans laquelle les occurrences futures sont matérialisées en DB. Fixé à **fin du mois en cours**, identique à l'horizon du solde projeté. Au-delà, les projections se font à la volée sans persistance (`forecast_with_recurrings(date_start, date_end)` utilisée par `forecasting/` et `savings/`).

**Génération** :
Job serveur exclusif (cron nightly via APScheduler) qui matérialise les occurrences manquantes jusqu'à l'horizon. Idempotent : `INSERT ... ON CONFLICT DO NOTHING` sur `(recurring_rule_id, occurrence_date)`. Pas de génération côté client ; pas de génération lazy.

### Soldes

**Solde réel** :
Somme des splits des transactions `confirmed` jusqu'à aujourd'hui.

**Solde prévisionnel** :
Solde réel + transactions `planned` jusqu'à `today + 7 jours`.

**Solde projeté** :
Solde réel + toutes les transactions `planned` jusqu'à **fin du mois en cours** (horizon fixe).

### Banking (intégration externe)

**`BankingProvider`** :
Protocol pull-only à 3 méthodes (`list_accounts`, `fetch_transactions`, `consent_status`) implémenté par `EnableBankingProvider`, `OFXProvider`, `MockProvider`. **Instancié et appelé uniquement par le job de polling** du module `banking`. Toute exception levée est typée (hiérarchie `BankingProviderError` : `ConsentExpiredError`, `ConsentRevokedError`, `ProviderUnavailableError`, `RateLimitedError`, `IncompatibleAccountError`).

**`BankingReader`** :
Protocol de lecture **synchrone depuis le cache DB locale** (`get_account`, `list_recent_transactions`, `last_sync_at`). Seule interface autorisée pour les consommateurs cross-module (reconciliation, MCP, dashboard). Matérialise dans le code l'invariant F14 *"jamais d'appel synchrone à Enable Banking"* — vérifiable par import-linter (seul `banking.service.polling` peut importer `BankingProvider`).

**`ConsentRef`** :
Référence opaque à un consentement DSP2 (id Enable Banking + métadonnées de cycle de vie SCA 180 jours). Persisté dans la table `bank_consents` du module `banking`. Renouvellement = nouvelle SCA → nouveau `ConsentRef`.

**Import OFX** :
Parser via `ofxparse` (avec wrapper défensif qui catch et re-raise en `BankingProviderError` typées) — supporte OFX 1.x SGML + OFX 2.x XML dès MVP. Détection d'encoding déterministe : BOM-first, puis tentative UTF-8 strict, puis fallback windows-1252. **Fallback windows-1252 = "détecté avec confiance" à False** → preview obligatoire (cf. critères F04). Dedup par **hash composite** `(account_id, date, amount, libellé_normalisé)`, FITID OFX ignoré (instable côté ASPSP français). Compte OFX non lié = preview obligatoire avec étape "lier à un compte interne existant" ou "créer le compte interne", **jamais de création automatique**. Mapping persistant dans `bank_account_external_refs`.

### Agent IA (MCP)

**PAT** (Personal Access Token) :
Jeton d'accès attaché à un utilisateur, hérite strictement de ses droits, jamais plus. Nommé, scopé (`read_only` / `read_write`), révocable, avec heuristiques de détection de compromission.
**Découpage code** : l'entité `PATToken` et l'auth de base par PAT vivent dans `modules/auth/` (avec JWT et refresh tokens) ; les heuristiques de compromission, le rate limiting par PAT, et l'audit MCP vivent dans `modules/mcp/`. Frontière : *auth = qui es-tu et qu'as-tu le droit de faire* ; *mcp = comment cet appelant agentique consomme l'API et dérape-t-il*.

**Module `mcp`** :
Module backend à part entière (cf. ADR 0004), orchestrateur consommateur des autres modules métier en lecture. Contient son propre `domain.py` (PendingAction, ActionLineage, CompromiseHeuristic), `service.py` (matérialisation, audit, rate limiter), `tools/` (un fichier par tool MCP), `transports/` (stdio + Streamable HTTP). **Sens d'import unidirectionnel : `mcp → autres modules` uniquement** ; aucun module métier ne dépend de `mcp`. Les tools `propose_*` créent des PendingAction et ne mutent jamais directement une entité métier ; la confirmation passe par les services métier normaux côté API.

**Pending action** :
Action proposée par un agent IA via MCP, en attente de confirmation humaine explicite. Entité de première classe, immutable, avec audit lineage.

**Audit lineage** :
Chaînage immutable entre une pending action originale et ses dérivées via `derived_from_action_id` / `superseded_by_action_id`. Une originale supplantée par `modify_then_confirm` passe à l'état terminal `superseded`.

**Squelette d'audit** :
Métadonnées d'une pending action conservées après purge du payload (timestamp, pat_id, tool_name, outcome, hash). Permet la détection rétroactive de patterns de compromission sans rétention de données sensibles.

### Architecture interne

**Public surface** (`public.py`) :
Fichier par module backend qui ré-exporte explicitement les types, fonctions et events destinés à un usage cross-module. Toute importation depuis `service.py`, `models.py`, `domain.py`, `repository.py` d'un autre module est interdite (vérifiée par import-linter). Chaque module est libre de ses internals.

**Graphe directionnel** (cf. ADR 0005, étendu par ADR 0014) :
Layers acycliques de bas en haut : `shared/` → `auth` → `accounts` → `{transactions, budget, banking}` → `{reconciliation, forecasting, debts, notifications}` → `sync` → `mcp`. Un module ne peut importer que des modules **strictement en-dessous**. Les deux sommets `sync` et `mcp` sont des orchestrateurs : `sync` ingère les mutations PowerSync (cf. write upload handler), `mcp` ingère les appels d'agents IA en lecture seule.

**Mini-bus in-process** (`shared/events.py`) :
Dispatcher synchrone in-process pour permettre aux modules métier (budget, banking, debts, auth…) de publier des `DomainEvent` typés sans importer `notifications`. Le module `notifications` souscrit aux events qui l'intéressent. Évite l'inversion du graphe directionnel sans introduire un bus distribué. Pas d'eventual consistency : le dispatch est synchrone dans la même transaction DB.

### Sync (PowerSync)

**Write upload handler** :
Pièce centrale du module `modules/sync/`. Reçoit le batch de mutations PowerSync, dispatch chaque mutation au sous-handler de sa table (`handlers/transactions.py`, etc.) qui appelle les `service.py` des modules métier via leur `public.py` (jamais d'écriture DB directe). Séquence stricte par mutation **dans une transaction DB unique** (sauf délivery email/push qui sort en `BackgroundTasks` post-commit) : auth & RBAC → idempotence check via `client_request_id` UUID v7 → Pydantic validation → domain validation → DB write → **matérialisation synchrone des projections** (dettes via `DebtCalculator`, cf. ADR 0002) → publication d'events sur le mini-bus → commit → append `sync_request_log` → ack. Cf. ADR 0014.

**`client_request_id`** :
UUID v7 généré localement par le client à chaque mutation, garantit l'idempotence en cas de retry après timeout réseau. Persisté dans `sync_request_log` (server-only, retention 30j).

**`WriteResult`** :
Réponse PowerSync par mutation, format `{success: bool, error?: {code, message}}`. Codes d'erreur typés : `validation_error` (Pydantic refusé), `immutable_field_violation` (édition d'un champ gelé d'aggregate `confirmed`, le client purge la mutation et resync), `auth_denied`, etc. Erreurs récupérables → client purge la mutation locale ; erreurs serveur inattendues (500) → PowerSync retry automatique.

**Bucket** :
Unité de découpage de la synchronisation PowerSync. Chaque bucket est paramétré par une identité (user_id, account_id, ou `household` global) et regroupe les rows qu'un appareil de ce périmètre a le droit de recevoir. Quatre familles utilisées :
- `user_personal_{user_id}` : comptes personnels, budgets perso, notifications, savings perso.
- `account_shared_{account_id}` : comptes communs, transactions/splits associés, account_members, budgets communs.
- `user_debt_{user_id}` : dettes et share_requests concernant cet utilisateur (débiteur ou créditeur).
- `household` : référentiels partagés à tout le foyer (categories, users_public).

**Server-only** :
Qualifie une table non sync via PowerSync, lue côté client uniquement via l'API REST (et SSE pour les évènements temps-réel). Concerne : `pending_actions`, `audit_logs`, `pat_tokens`, `users` (PII complète).

**`users_public`** :
Sous-ensemble de l'identité utilisateur synchronisé au foyer : `user_id`, `display_name`, `avatar_url`, `role`. Permet d'afficher "demandé par Alice" sans dupliquer en snapshot. Pas de PII.

### Notifications & temps-réel

**Canal** :
Surface de livraison d'une notification : `email`, `push` (FCM via `@capacitor/push-notifications`), `in_app` (table sync `notifications`), `sse` (web temps-réel). Modules métier publient des `DomainEvent` via `shared/events.py` ; le `notifications.dispatcher` consomme, applique la matrice de préférences, dispatche aux canaux souscrits.

**SSE stack** :
`sse-starlette` côté FastAPI. **Auth via JWT short-lived en query param** (l'API `EventSource` n'accepte pas de headers custom) : le client fait `POST /sse/token` (auth JWT normale) pour obtenir un token scope `sse_subscribe` valide 5 min, qu'il passe à `GET /sse/stream?token=...`. **Heartbeat 30s** (sous les 100s idle Cloudflare). **Resume après disconnect** via `Last-Event-ID` header standard + buffer ring 5min/100 events par utilisateur côté serveur ; au-delà, le client doit re-sync via REST. Cf. ADR 0012.

**Préférences notifications** :
Table `notification_preferences (user_id, event_type, channel, enabled)`, sync `user_personal_{user_id}`. Defaults sensibles au premier login. **Événements sécurité hardcoded non-désactivables côté code** (`pat_compromised`, `pat_alert`, `mcp_action_pending` push) — le dispatcher ignore les rows de préférences pour ces event_types.

**`device_tokens`** :
Table server-only (PII : tokens FCM) qui mappe `(user_id, platform, token, registered_at)`. Auto-purge sur réponse FCM `unregistered`. Push V1 = Android only via plugin Capacitor officiel.

**Email stack** :
SMTP générique configurable par env (`SMTP_HOST`, `SMTP_USER`, etc.), `aiosmtplib` côté serveur, templates Jinja2 dans `notifications/templates/`. Provider par défaut recommandé : Brevo free tier 300/j (volume V1 très bas), mais le code ne sait rien du provider — switch trivial.

**Column-level filter (sync rule)** :
Mécanisme où la requête de bucket sélectionne explicitement `NULL AS <column>` pour masquer un champ selon le destinataire. Utilisé pour `source_transaction_id` sur les dettes `personal_share_request` : le débiteur ne le reçoit jamais, seul le propriétaire du compte personnel source le voit.

## Flagged ambiguities

_(à remplir au fil du grilling)_

## Example dialogue

> **Dev** : Tiens, on a une transaction de 80€ payée par Alice depuis son compte courant personnel pour des courses communes. Comment Bob voit ça ?
>
> **Domain expert** : Si Alice ne fait rien, Bob ne voit rien. Le compte courant d'Alice est personnel, donc invisible pour Bob — même l'admin n'y a pas accès. Si Alice veut partager, elle crée explicitement une **demande de partage** sur cette transaction : ça matérialise une **dette** d'origine `personal_share_request` de 40€ de Bob vers Alice.
>
> **Dev** : Et Bob voit quoi exactement ?
>
> **Domain expert** : La dette. Pas la transaction source. Il voit `from: Bob, to: Alice, amount: 40€, category: Courses, date, requested_by: Alice, libellé: "courses Monoprix"` — le libellé court qu'Alice a écrit dans la demande. La transaction Monoprix elle-même, avec son montant complet et sa pièce jointe éventuelle, reste invisible pour Bob.
>
> **Dev** : Et si Alice avait payé depuis le compte commun ?
>
> **Domain expert** : Alors c'est un autre cas — `shared_account_overflow`. Le compte commun absorbe la dépense dans la limite du budget restant. Seul l'**excédent** au-delà du budget alimente une dette, réparti selon la **quote-part** du compte (50/50 par défaut). La transaction reste visible par tous les membres du compte commun.
