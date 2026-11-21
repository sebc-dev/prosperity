# Feature Research

**Domain:** Finances partagées d'un foyer, dont la seule interface est Claude (conversation + artefacts claude.ai) via un connecteur MCP distant
**Researched:** 2026-11-21
**Confidence:** MEDIUM-HIGH (HIGH sur les capacités Claude/MCP Apps/artefacts, vérifiées dans les docs officielles et les définitions de types du runtime ; MEDIUM sur l'analyse concurrentielle, faite de mémoire et non re-vérifiée en ligne, hors serveurs MCP communautaires)

> Référence métier : `origin/main:CONTEXT.md` + ADR 0001/0002/0004/0011/0013. Le domaine n'est pas ré-inventé ici, il est projeté sur la nouvelle interface. Les termes métier gardent leur vocabulaire (Foyer, Compte commun, Quote-part, Split, Pointage, Settlement, Excédent budgétaire, `debt_generation_override`).

## Constats structurants (à lire avant le reste)

1. **Le domaine de Prosperity est plus riche que celui de tous les concurrents sur un axe précis** : dettes calculées côté serveur à partir d'un budget (F10), cloisonnement dur des comptes personnels, règlements multi-lignes. Aucun concurrent grand public ne combine budget + dettes de foyer + compte personnel étanche. C'est le coeur différenciant, et il existe déjà dans le modèle. Le travail nouveau porte sur la surface MCP, pas sur le domaine.
2. **Deux chemins d'UI sont publiquement documentés et ne se valent pas** (détail section "Artefacts vs MCP Apps") : les artefacts avec capacité `mcp` (identité du lecteur, consentement par lecteur, partageables) et MCP Apps (UI fournie par le serveur, outils `visibility: ["app"]` invisibles du modèle). Les outils doivent être conçus **indépendants de l'UI** : agrégats `structuredContent` prêts à afficher, qui servent les deux.
3. **Le canal de confirmation est le point de sécurité central.** Un `confirm_pending_action` appelable par le modèle peut être déclenché par une injection de prompt (une description de transaction importée suffit). Seuls deux mécanismes séparent "l'humain a cliqué" de "le modèle a décidé" : le prompt natif de Claude pour les outils `destructiveHint: true`, et les outils MCP Apps `visibility: ["app"]`. La politique d'écriture doit s'appuyer dessus (section "Politique d'écriture").
4. **Idempotence obligatoire sur toute écriture.** Le contrat runtime des artefacts dit explicitement qu'un rejet `server_unavailable`/`upstream_error` sur une écriture "n'est PAS la preuve que l'outil n'a pas tourné". Sans clé d'idempotence, un retry fait un doublon de dépense. Le journal `sync_request_log` de l'ancien ADR 0014 est le précédent à reprendre.
5. **Pas de push.** Sans UI propre, pas de notifications, pas de SSE. Les alertes de seuil budgétaire (80 %/100 %) deviennent des données lues à l'ouverture (dashboard, réponse des outils d'écriture), pas des événements poussés.

---

## Feature Landscape

Légende complexité : LOW (< 1 phase, mécanique) / MEDIUM (1 phase, logique métier) / HIGH (plusieurs phases ou risque d'intégration). Légende statut dans le domaine : **[M]** = déjà modélisé dans CONTEXT.md, **[N]** = nouveau côté MCP/Claude.

### 1. Foyer & accès

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Connecteur MCP distant : HTTPS public + OAuth conforme spec d'autorisation MCP, ajoutable comme connecteur personnalisé claude.ai [N] | Prérequis de tout. Les connecteurs personnalisés se déclarent par URL ; Claude se connecte depuis l'infra Anthropic (un `localhost` est injoignable) | HIGH | Exposition par tunnel (Cloudflare Tunnel prévu). Les docs Anthropic demandent OAuth 2.0 pour les outils agissant sur un compte. Le flux d'auth est le seul "écran web" toléré |
| Identité par membre de bout en bout : chaque outil filtre sur l'utilisateur OAuth authentifié, jamais sur un argument fourni par Claude [N] | Données financières réelles ; exigence héritée non négociable | MEDIUM | Aucun paramètre `user_id` dans les outils. L'identité vient du jeton |
| Foyer de N membres, rôles admin/member [M] | Base de tout produit foyer (Splitwise : groupes ; YNAB : partage de budget) | LOW | Foyer singleton (ADR 0010). Un déploiement = un foyer |
| Bootstrap du premier admin et invitations (token hashé, 7 jours, rôle toujours `member`) [M] | Sans lui, personne ne peut entrer | MEDIUM | À adapter : l'ancien `/setup` web disparaît. Le bootstrap passe par l'écran OAuth (premier compte = admin si `users` vide, verrou après init) ou un secret d'environnement. L'invitation devient un lien/code consommé à l'écran d'autorisation OAuth |
| Cloisonnement strict compte personnel (même l'admin n'y accède pas) [M] | Argument central de confiance du foyer | MEDIUM | Filtrage dans la couche service, couvert par tests de propriété (aucun outil ne renvoie un compte non accessible). L'oracle de l'`ImportPreview` (INV-S12.3) reste à fermer : non-disclosure uniforme |
| Révocation d'accès d'un membre et de ses jetons [N] | Un membre qui quitte le foyer doit perdre l'accès immédiatement | LOW | Révocation de la session OAuth côté serveur ; le connecteur côté claude.ai se reconnecte à la demande |
| Découverte du contexte par Claude : qui suis-je, quels comptes, quel foyer, quelle devise, quelle politique d'écriture [N] | Sans contexte, Claude devine les noms de comptes/catégories et se trompe | LOW | Un outil `get_household_context` + le champ `instructions` du serveur. Voir section "Surface MCP" |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Connecteur nommé de façon conventionnelle pour tout le foyer (`Prosperity`) afin qu'un artefact partagé fonctionne pour chacun [N] | Un tableau de bord publié une fois est consommé par chaque membre avec **ses propres** droits (la capacité `mcp` référence le connecteur par son **nom d'affichage**) | LOW | Contrainte d'onboarding à documenter. Voir section artefacts |
| Politique d'écriture configurable par membre (voir section dédiée) [N] | Fluidité pour l'un, prudence pour l'autre, dans le même foyer | MEDIUM | Aucun concurrent n'a ce concept : il n'existait pas d'agent |
| Journal d'audit consultable par le membre : "qu'a fait Claude en mon nom ?" [N] | Confiance dans un agent qui écrit des données financières | MEDIUM | Voir section "Audit" |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Admin qui peut lire les comptes de tous ("pour dépanner") | Support facile | Casse le cloisonnement, vecteur de takeover silencieux (même raisonnement que l'ADR 0013) | Admin = droits et invitations uniquement, jamais les données. Reset par accès physique à la machine |
| Reset de 2FA/identité par l'admin via l'outil | Confort | Takeover silencieux d'un compte | Reset documenté en runbook (accès machine) |
| PAT, 2FA TOTP maison, mot de passe maison | Héritage de l'ancien backend | OAuth délègue l'authentification ; Claude est le seul client | Déléguer à un IdP (ou un OAuth minimal self-hosted), pas de gestion de mot de passe ni de TOTP dans le backend si évitable. Question ouverte pour la phase stack |
| Multi-foyers par instance | "Pour les amis" | Casse l'invariant singleton et multiplie la surface de cloisonnement | Une instance par foyer |
| Inscription publique | Facilité | Ouvre l'instance au monde | Invitation seulement |

---

### 2. Comptes & transactions

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Comptes personnels et communs, quotes-parts par membre (défaut 50/50) [M] | Splitwise/Tricount ont les parts ; YNAB/Actual/Firefly ont les comptes multiples | MEDIUM | `default_share_ratio` par membre dans `account_members` |
| Catégories hiérarchiques, archivage au lieu de suppression, prévention de cycle [M] | Table stakes chez tous (YNAB groupes, Firefly, Actual) | MEDIUM | Réorganisation libre, les agrégats suivent. Audit de l'opération |
| Transactions à splits zero-sum, états `draft/planned/confirmed/void`, aggregate immuable à `confirmed` (correction = `void` + nouvelle) [M] | Double-entrée (Firefly III, Actual) ; l'immutabilité simplifie le raisonnement d'un agent : pas d'édition de montant | HIGH | Le coeur du modèle. Reprendre ADR 0001/0017 tel quel. Édition post-`confirmed` limitée à `category_id`, `tags`, `description`, `debt_generation_override`, `share_request` |
| Value object Money (centimes entiers + devise), usage verrouillé EUR (`household.base_currency`) [M] | Exactitude ; ADR 0008 | LOW | Jamais de flottant dans les outils : montants en centimes entiers ET libellé formaté fourni par le serveur |
| Soldes réel / prévisionnel (+7 j) / projeté (fin de mois) [M] | Affichage standard d'un compte (Bankin', Linxo, Actual) | MEDIUM | Le projeté dépend des transactions `planned`, donc des récurrences (voir 4) |
| Tags libres en plus des catégories [M] | Firefly/Actual | LOW | Éditable après `confirmed` |
| Recherche/filtre de transactions (période, compte, catégorie, montant, texte, tag) [N] | Impossible de répondre à "où est passé le paiement du plombier" sans | MEDIUM | Outil de lecture paginé, borné (taille de réponse raisonnable, exigence de revue Anthropic) |
| Récurrences (`recurring_rule` → occurrences `planned`, job serveur idempotent, horizon fin de mois) [M] | YNAB/Actual schedules, Firefly recurring, Bankin'/Linxo "prochaines échéances" | MEDIUM | **Absent de la liste Active de PROJECT.md alors que présent dans CONTEXT.md/ADR 0007.** À trancher en définition des exigences. Recommandation : v1.x (le projeté et la projection d'épargne en dépendent, pas le coeur de saisie) |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Immutabilité comme garde-fou d'agent : Claude ne peut pas "réécrire l'histoire", seulement `void` + recréer, ce qui se voit dans l'audit [M] | Un agent qui se trompe laisse une trace correctable, pas une mutation silencieuse | LOW (déjà dans le modèle) | Argument de vente et de sécurité, à documenter dans les descriptions d'outils |
| Réponses d'écriture "riches" : chaque outil d'écriture renvoie l'état résultant (nouveau solde, consommation du budget, dette générée, alerte de seuil franchi) [N] | Claude confirme en une phrase exacte sans second appel ; les alertes 80 %/100 % arrivent au moment où elles comptent | MEDIUM | Remplace les notifications push |
| Recherche tolérante de catégorie/compte/membre par nom ("courses" → Alimentation > Courses) avec renvoi d'ambiguïté structuré [N] | La saisie conversationnelle échoue si Claude doit connaître des UUID | MEDIUM | Voir "Saisie via Claude" |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Édition libre du montant/des splits d'une transaction `confirmed` | "Juste corriger une faute de frappe" | Casse la double-entrée et la matérialisation idempotente des dettes | `void` + nouvelle transaction (un seul outil composite `correct_transaction` qui enchaîne les deux dans une action) |
| Hard-delete de catégorie/compte/transaction | Ménage | Perte d'historique, agrégats faux | Archivage ; `void` |
| Catégorie "Sans catégorie" magique | Import rapide | Fausse les budgets (ADR E06) | Brouillon `draft` + pointage/triage explicite |
| Multi-devise en usage | "On part en voyage" | Hors périmètre v1 (ADR 0008) ; le modèle reste multi-devise | Verrou EUR |
| Outil générique `run_sql` / `api_request(method, path)` | Souplesse maximale pour Claude | Contourne cloisonnement et audit ; **rejeté explicitement par les critères de revue Anthropic** (outil mêlant lecture et écriture) ; surface d'injection énorme | Outils étroits, lecture/écriture séparées |

---

### 3. Saisie via Claude

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Saisie en une phrase : "j'ai payé 84 € de courses, partagé 50/50" → transaction créée [N] | C'est la Core Value du projet | MEDIUM | Un outil `create_transaction` à paramètres haut niveau (montant, compte payeur, catégorie par nom, mode de partage), qui construit les splits zero-sum côté serveur. Claude ne calcule aucun split |
| Résolution par nom avec ambiguïté structurée : si "courses" correspond à 2 catégories, l'outil renvoie `needs_clarification` + candidats (pas une devinette, pas un échec opaque) [N] | Évite les erreurs silencieuses de catégorie | MEDIUM | Erreurs actionnables (critère de revue Anthropic : "pas d'erreur générique") |
| Idempotence des écritures (`idempotency_key` fournie par l'appelant ou dérivée) [N] | Retries ambigus documentés dans le contrat runtime ; doublons de dépenses sinon | MEDIUM | Reprendre `sync_request_log` (PK composite `(user_id, key)`), rétention 30 j |
| Échec propre et message précis : codes d'erreur d'un vocabulaire fermé (validation, état invalide, immuable, non autorisé, ambigu) [M→N] | Claude doit savoir quoi dire à l'utilisateur | LOW | S'inspirer de `WriteErrorCode` (ADR 0014), `message` statique par code, sans PII |
| Annulation de la dernière saisie : "oublie, c'est la mauvaise" → `void` de la transaction créée dans la session [N] | Le geste naturel après une erreur de saisie | LOW | S'appuie sur `void` ; classé "risque faible" dans la politique si la transaction a été créée par l'agent dans les dernières minutes |
| Création en `draft`/`planned` ou `confirmed` selon intention explicite | "J'ai payé" vs "on doit payer" | LOW | Défaut `confirmed` pour "j'ai payé", `planned` pour futur |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Photo de ticket de caisse → transaction (Claude lit l'image via sa vision, appelle `create_transaction` avec splits par catégorie) [N] | Splitwise le réserve à Pro (receipt scanning), Tricount ne fait que joindre la photo. Ici la vision est native : zéro OCR à construire | LOW | Dépend de `create_transaction` multi-splits. Confirmer avant écriture si montant lu à faible confiance. Pas de stockage de la photo en v1 |
| Saisie multiple en une phrase ("courses 84 €, essence 60 €, resto 45 € hier") [N] | Rapide, naturel | MEDIUM | Outil batch avec résultat par ligne et atomicité par ligne (échec partiel explicite) |
| Prévisualisation avant écriture dans les modes `propose`/risque (voir section politique) : l'effet attendu (dette générée, budget consommé) est calculé par le serveur et montré *avant* confirmation [N] | La confirmation devient informée, pas un "OK" aveugle | MEDIUM | Réutilise `DebtCalculator` en mode lecture seule (dry-run) |
| Saisie guidée par artefact : formulaire à listes de comptes/catégories réelles, avec défauts mémorisés [N] | Pour qui préfère un formulaire à la phrase | MEDIUM | Voir "Interfaces artefacts" |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Claude calcule les splits/dettes/parts lui-même puis envoie les résultats | Moins d'outils | LLM faux en arithmétique ; viole la contrainte "les chiffres font foi côté serveur" | L'outil prend une intention (`partage: 50/50`, `payeur`) et calcule |
| Création de catégories "à la volée" par Claude à chaque saisie | Fluidité | Prolifération de catégories ("Courses", "courses ", "Supermarché") | Si pas de correspondance : `needs_clarification` avec proposition, création via outil distinct soumis à politique |
| Mémoire inter-sessions des préférences stockée côté Claude | Confort | Non fiable, non auditable, non partagée | Préférences stockées côté serveur (compte par défaut, partage par défaut) lues par `get_household_context` |

---

### 4. Budgets

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Budget par catégorie et période (mensuel par défaut), scope perso ou commun, contributeurs [M] | Table stakes de YNAB/Actual/Firefly/Bankin' | MEDIUM | Agrège les sous-catégories. Budget perso jamais appliqué à un compte commun |
| Consommation et restant par budget, par période, avec statut (OK/seuil/dépassé) [M] | La question n°1 : "où en est-on ?" | MEDIUM | Agrégat prêt à afficher, calculé serveur. Restant R borné à ≥ 0, ordre total `(date, id)` (F10) |
| Alertes de seuil 80 %/100 % [M] | Standard (Bankin', Linxo) | LOW | **Pas de push** : remontées dans les réponses d'écriture et dans `get_alerts`/dashboard. L'événement `budget_threshold_crossed` existe côté serveur et alimente ces deux surfaces |
| Création/modification/archivage de budget avec reclassement F10 (re-matérialisation des dettes passées) [M] | Cohérence dettes ↔ budget | HIGH | Le balayage non borné en temps est une limite V1.5 connue du modèle. Les trois opérations passent par la politique d'écriture (risque moyen : elles réécrivent des dettes) |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Budget qui fabrique la dette (F10) : l'excédent budgétaire sur compte commun devient une dette de quote-part [M] | Aucun concurrent ne relie budget commun et dettes entre membres | HIGH (déjà spécifié) | Argument de vente majeur ; le plus risqué à porter sur MCP à cause du reclassement rétroactif |
| "Et si ?" avant modification : simuler l'effet d'un changement de budget sur les dettes existantes avant de l'appliquer [N] | Rend le reclassement F10 sûr pour un agent | MEDIUM | Dry-run du reclassement ; indispensable avant d'autoriser `direct` sur `update_budget` |
| Suggestion de budget à partir de l'historique ("ta moyenne restaurants sur 3 mois est de 210 €") [N] | Claude excelle ici, le serveur fournit les agrégats | LOW | Outil d'analyse de lecture ; la décision reste humaine |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Méthodologie enveloppe complète type YNAB (assigner chaque euro, rollover, "age of money") | Popularité de YNAB | Autre produit, autre modèle mental ; le budget Prosperity est un plafond par catégorie qui alimente les dettes | Budget = plafond + consommation ; pas de report d'enveloppe en v1 |
| Auto-ajustement silencieux des budgets par Claude | "Optimisation" | Réécrit des dettes (F10) sans que personne ne le voie | Proposition seulement, jamais d'écriture directe par défaut |
| Notifications push/email d'alerte | Standard des apps bancaires | Pas d'UI propre, hors scope v1 | Alertes lues à l'ouverture et dans les réponses d'écriture. Email post-v1 si le besoin est réel |

---

### 5. Dettes & règlements

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Vue "qui doit quoi à qui" par membre, solde net, détail par dette [M] | Coeur de Splitwise/Tricount | MEDIUM | Projection serveur en lecture seule (ADR 0002). Solde d'une dette = montant − Σ lignes de règlement |
| Origine de dette : `shared_account_overflow` (compte commun, via F10) et `personal_share_request` (demande de partage explicite depuis un compte perso) [M] | Cloisonnement + partage | HIGH | Un compte perso ne génère jamais de dette implicitement |
| Visibilité masquée côté débiteur d'une `personal_share_request` : voit montant, catégorie, date, demandeur, libellé court ; jamais la transaction source ni le compte source [M] | Étanchéité du compte perso | MEDIUM | Masquage de colonnes dans la couche de lecture (équivalent MCP du filtre de colonnes PowerSync). Test dédié sur chaque outil renvoyant des dettes |
| Création d'une demande de partage avec libellé court [M] | Seul chemin d'un compte perso vers une dette | LOW | Sous politique d'écriture : engage un autre membre, donc plus sensible qu'une saisie |
| Règlement multi-dettes : virement interne, virement externe, compensation virtuelle ; lignes de règlement, nettage croisé bidirectionnel [M] | Splitwise "settle up", Tricount "rembourser" | HIGH | ADR 0011. Un règlement apure N dettes via N `SettlementLine` |
| Leviers utilisateur limités : `share_ratio` par dette, `debt_generation_override` (`default`/`force_full_debt`/`force_no_debt`), règlement [M] | Seuls leviers d'écriture, tout le reste est projection | MEDIUM | Peu d'outils d'écriture = surface agent réduite : c'est un atout |
| Suggestion de règlement optimal ("pour solder, Bob vire 132 € à Alice") [N] | Splitwise "simplify debts", Tricount "suggestions de remboursement" | MEDIUM | Calcul serveur du plan de règlement net ; Claude le présente. Attention : ne pas perdre la traçabilité par dette (le nettage doit rester ligne à ligne) |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Règlement proposé puis confirmé par les deux parties concernées [N] | Un règlement engage deux membres ; deux accords évitent le "j'ai dit que Bob m'avait remboursé" | HIGH | Étend la `PendingAction` à un second approbateur. À arbitrer : v1 = confirmation par l'initiateur + visibilité par la contrepartie ; double accord = v1.x |
| Explication d'une dette en langage naturel ("cette dette de 23 € vient du dépassement du budget Restaurants de mars, quote-part 50 %") [N] | Transparence sur un calcul complexe (F10) | MEDIUM | Outil d'analyse `explain_debt` qui renvoie la chaîne causale structurée ; Claude la raconte. Respecte le masquage côté débiteur |
| Rapprochement règlement ↔ virement bancaire importé (le règlement `internal_transfer` se pointe avec la ligne bancaire) [M] | Boucle fermée dettes ↔ banque | HIGH | Dépend d'Import & pointage |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Dette éditable directement (montant, parties) | "Corriger une erreur" | Viole la projection (ADR 0002) | Corriger la transaction source (`void` + nouvelle) ou ajuster `share_ratio` |
| Règlement automatique par virement réel | Confort | Hors périmètre (aucun mouvement d'argent réel) ; **les connecteurs qui transfèrent de l'argent sont exclus des annuaires Anthropic** | Le règlement enregistre un fait ; l'argent bouge hors Prosperity |
| "Simplifier les dettes" en fusionnant des dettes entre plus de 2 personnes sans trace | Splitwise le fait | À 2-4 membres la valeur est faible et la traçabilité par dette se perd | Nettage croisé par `SettlementLine`, qui reste auditable |
| Rappels de dettes automatiques ("Bob te doit encore 40 €") | Pression sociale | Pas de push ; ton intrusif dans un foyer | Visible à l'ouverture du dashboard |

---

### 6. Import & pointage

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Import de fichier OFX (1.x SGML + 2.x XML) et CSV avec détection d'encodage, preview obligatoire sur fallback windows-1252 [M] | Tous les concurrents (Actual, Firefly, YNAB, Linxo) | HIGH | Parser défensif ; erreurs typées. CSV absent de l'ancien modèle (OFX seulement) : le mapping de colonnes est du travail nouveau |
| Dédup par hash composite `(account_id, date, amount, libellé normalisé)`, FITID ignoré [M] | Réimporter un relevé sans doublons | MEDIUM | `UNIQUE(import_hash)` en backstop, commit idempotent |
| Lien compte du fichier ↔ compte interne, jamais de création automatique [M] | Évite l'import sur le mauvais compte | MEDIUM | Gate d'accessibilité + non-disclosure uniforme (INV-S12.3) |
| Commit atomique en `draft` (jamais `confirmed`) ; catégorisation ensuite [M] | Invariant d'immutabilité | MEDIUM | Une jambe `funding` seule en `draft` ; ADR E12 |
| Pointage : suggestions de rapprochement transaction locale ↔ ligne bancaire, confirmées par l'utilisateur [M] | YNAB "reconcile", Actual "reconciled", Firefly rules | HIGH | `Reconciliation` entité distincte (ADR 0006) ; `MatchScorer` (date + libellé rapidfuzz + montant strict) |
| Pas d'auto-confirm du pointage, quel que soit le score [M] | Décision produit actée | LOW | Ne **jamais** exposer un chemin "direct" pour `confirm_reconciliation` dans la politique d'écriture (plancher non configurable) |
| Dépointage sans retour à `planned` (annuler = `void` + recréer) [M] | Cohérence avec l'immutabilité | LOW | |
| Transport du fichier jusqu'au serveur [N] | Un relevé n'est pas une saisie de chat | HIGH | **Point de faisabilité central, voir "Import et fichiers" ci-dessous** |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Triage assisté par Claude : Claude propose une catégorie par ligne importée à partir du libellé et de l'historique, le membre valide en lot dans un écran de tri [N] | Remplace le moteur de règles d'Actual/Firefly par une catégorisation sémantique, sans configuration | MEDIUM | Claude propose, le serveur n'écrit rien sans validation. Les validations alimentent une table "libellé normalisé → catégorie" pour une suggestion déterministe ensuite |
| Mémoire de catégorisation déterministe (libellé normalisé → catégorie confirmée) [N] | Réduit l'appel au modèle sur les récurrents (loyer, abonnements), rend la suggestion explicable | MEDIUM | `normalize_label` partagé avec `MatchScorer` et la dédup (source unique, cf. CONTEXT) |
| Agrégation DSP2 (Enable Banking / GoCardless) en plus du fichier [M] | Bankin'/Linxo/Finary : flux continu sans export manuel | HIGH | Polling serveur uniquement (invariant F14 : jamais d'appel synchrone à l'agrégateur depuis un outil). Consentement SCA à renouveler à 90/180 j : un outil de lecture `get_bank_consent_status` + lien de renouvellement à ouvrir par l'humain |
| Explication d'une suggestion de pointage ("même montant, libellé proche à 82 %, 1 jour d'écart") [N] | Rend la validation rapide et sûre | LOW | Le score reste interne en V1 (CONTEXT), seule la raison textuelle est exposée |
| Détection d'anomalies à l'import (montant atypique, doublon probable inter-fichiers, date hors plage) via les 5 critères F04 [M] | Sécurité de l'import | LOW | `AutoValidationCriteria` informatif ; la décision reste humaine |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Auto-confirm du pointage au-dessus d'un score | Gain de temps | Décision produit actée : user-in-the-loop strict | Validation en lot dans l'écran de triage (un geste pour N suggestions, mais explicite) |
| Passer le contenu d'un relevé dans le contexte de Claude (coller le CSV dans le chat et laisser Claude appeler `create_transaction` ligne par ligne) | "Ça marche sans UI" | Coût en tokens énorme, troncature, hallucination de lignes, N appels non atomiques, **et injection de prompt via les libellés bancaires** | Fichier envoyé tel quel au serveur (argument fichier de `callTool` depuis l'artefact), parsé côté serveur, Claude ne voit que le résumé et les lignes à trier |
| Appel synchrone à l'agrégateur bancaire depuis un outil MCP | Données fraîches | Latence, quotas, consentements, invariant F14 | Cache DB local alimenté par le job de polling ; l'outil lit le cache (`BankingReader`) |
| Stockage de crédentials bancaires | "Connexion directe" | Responsabilité légale et risque | Agrégateur agréé DSP2 uniquement |

---

### 7. Épargne

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Objectif d'épargne (nom, cible, date, versement mensuel cible) [M] | Firefly "piggy banks", Linxo/Bankin' objectifs, YNAB targets | LOW | |
| Allocations d'un objectif sur N comptes, pas de "solde libre" matérialisé (calculé à la lecture), auto-cap proportionnel avec avertissement [M] | Modèle actuel | MEDIUM | Aucune erreur bloquante sur sur-allocation, seulement un warning dans la réponse |
| Versement rattaché à un objectif (`split.savings_goal_id`) [M] | Suivi des versements réels | LOW | |
| Projection sur 90 jours glissants, états `en_avance`/`dans_les_temps`/`en_retard`, masquage < 30 j, badge "estimation provisoire" 30-90 j [M] | Réponse à "on y arrive à quelle date ?" | MEDIUM | `ProjectionCalculator` serveur ; Claude ne projette rien |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "Combien mettre par mois pour atteindre la cible à la date ?" et "que se passe-t-il si je saute ce mois ?" [N] | Questions typiques de conversation, que le serveur calcule en déterministe | LOW | Outil d'analyse `simulate_savings` (lecture seule) |
| Vue foyer des objectifs communs avec contribution par membre [N] | Dimension foyer absente des apps individuelles (Finary, Bankin') | MEDIUM | Dépend des comptes communs et quotes-parts |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Suivi de portefeuille, bourse, immobilier, patrimoine net (Finary) | "Vue globale du patrimoine" | Produit différent (agrégation de courtiers, valorisations externes) ; hors Core Value | Aucun en v1. Comptes d'épargne simples uniquement |
| Rendement/performance projetés | Attrait | Conseil financier implicite, données externes | Projection = rythme observé, pas de rendement |

---

### 8. Interfaces artefacts

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Tableau de bord : soldes, budgets (consommation/alertes), dettes en cours, épargne, dernières transactions, alertes [N] | Premier écran de tout produit financier | MEDIUM | `watchTool` sur un petit nombre d'outils de lecture agrégés (1 à 3), jamais un appel par widget (limite de 64 watches par vue, coalescence par identité) |
| Formulaire de saisie (montant, compte, catégorie, partage, date) [N] | Complète la phrase quand on veut tout voir | MEDIUM | `callTool` sur geste explicite ; clé d'idempotence générée par le formulaire |
| Écran de dettes & règlements : soldes nets, détail, plan de règlement suggéré, bouton "enregistrer le règlement" [N] | Équivalent du "settle up" | MEDIUM | Écriture soumise à la politique : si `propose`, l'écran affiche l'action en attente |
| Écran de triage d'import : dépôt de fichier, preview (compteurs, doublons, plage de dates, 5 critères), lignes à catégoriser/pointer, validation en lot [N] | Sans lui, pas d'import praticable depuis Claude | HIGH | Dépôt de fichier via l'argument `$file` de `callTool` (si `fileArgs` est vrai ; limite 16 Mio). Le plus complexe des écrans |
| Écran d'actions en attente : liste, aperçu d'effet, confirmer / refuser / modifier puis confirmer [N] | Rend la politique `propose` utilisable | MEDIUM | Voir section politique. Prérequis de tout mode `propose` |
| États dégradés par code d'erreur : connecteur non connecté, besoin de réauth, consentement refusé, `approval_required`, données périmées avec fraîcheur (`cache.storedAt`) [N] | Exigence du contrat runtime ; sans elle l'artefact est un écran vide | MEDIUM | Sections indépendantes : une section en échec ne vide pas les autres |
| Écran de budgets (consommation, restant, alertes, édition) et d'épargne (objectifs, allocations, projection) [N] | Parité fonctionnelle avec l'ancien client | MEDIUM | Peut être livré plus tard que dashboard/saisie/triage |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Un artefact partagé au foyer, chaque membre voyant **ses** données (les appels passent par le compte du lecteur) [N] | Un seul tableau de bord pour tout le foyer, cloisonnement préservé de fait | LOW | Propriété native de la capacité `mcp` ; exige le même nom de connecteur chez tous. Non disponible pour un lecteur anonyme d'un lien public |
| Gabarits d'artefacts distribués par le serveur (ressources/prompts MCP) que Claude publie tels quels [N] | UI stable d'une session à l'autre, moindre coût en tokens, pas de dérive visuelle | MEDIUM | Sinon Claude régénère l'écran à chaque demande, avec variations et risque de bug sur l'écriture. Voir "Surface MCP" |
| Rafraîchissement après écriture : `invalidate` ciblé puis `watchTool` re-livre | UI cohérente après action | LOW | |
| Export CSV du relevé ou d'un rapport via la capacité `downloads` [N] | Comptabilité, impôts | LOW | Capacité à déclarer ; l'enregistrement est toujours soumis à confirmation du lecteur |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Artefact qui calcule (dettes, restants, totaux) | "Plus réactif" | Contredit "les chiffres font foi côté serveur" ; divergence entre écrans | L'artefact ne fait que rendre des agrégats ; formatage seul côté client |
| Stocker des données financières dans la base de l'artefact (`db`, `artifact`) | Persistance gratuite | Données hors du backend, hors cloisonnement, partagées avec quiconque a le lien | Tout l'état financier reste dans le backend ; l'artefact n'a que de l'état d'UI |
| Écriture déclenchée au chargement, sur minuteur ou par `watchTool` | "Synchro automatique" | `watchTool` refuse les outils non en lecture seule ; une écriture hors geste est un risque majeur | `callTool` uniquement sur clic explicite, une fois |
| Un appel `callTool` par ligne sans idempotence | Simplicité | Doublons sur retry ambigu | Clé d'idempotence par action ; endpoint batch avec résultat par ligne |
| Lien public sur un artefact connecté | Partage externe | Les appels connecteur ne tournent pas pour un lecteur anonyme ; fausse impression de partage | Partage dans l'organisation/le foyer uniquement |

---

### 9. Analyse

#### Table stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Dépenses par catégorie/période/compte/membre, avec comparaison à la période précédente [N] | Rapport standard (YNAB, Actual, Bankin', Linxo) | MEDIUM | `analyze_spending` ; renvoie des tables, jamais des conclusions chiffrées par le modèle |
| Évolution des soldes et projection (réel/prévisionnel/projeté) [M] | | MEDIUM | Dépend des récurrences pour le projeté |
| Top dépenses, plus grosses transactions, commerçants récurrents [N] | Questions fréquentes | LOW | Requêtes bornées en taille |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "Pourquoi on a dépassé en restaurants ?" : outil d'explication qui renvoie les contributeurs (transactions les plus lourdes, ratio vs moyenne, jours de pic, qui a payé), que Claude narre [N] | Seul domaine où un LLM bat un tableau de bord : question ouverte + données exactes serveur | MEDIUM | Cible d'usage de PROJECT.md. Sortie structurée avec identifiants, le modèle n'invente aucun chiffre |
| Revue mensuelle du foyer (prompt MCP `point_mensuel`) : budgets, dettes, épargne, anomalies en un récit court [N] | Rituel de couple/foyer ; aucune app ne le produit | MEDIUM | Assemble des outils existants, pas de logique propre |
| Détection d'anomalies et d'abonnements oubliés (même commerçant, même montant, récurrent) [N] | Bankin'/Linxo premium le font | MEDIUM | Calcul serveur déterministe, sans modèle |
| Questions en langage libre sur l'historique via outils étroits composables (filtre + agrégat) [N] | Remplace des dizaines de rapports prédéfinis | MEDIUM | Un petit nombre d'outils paramétrables bat 80 outils (voir "Surface MCP") |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Conseil d'investissement ou fiscal | "IA financière" | Responsabilité, hors périmètre | Descriptif uniquement |
| Calcul de moyennes/totaux par le modèle à partir de listes brutes | Moins d'outils d'agrégat | Erreurs arithmétiques, contraire à la contrainte d'exactitude | Agrégats serveur seulement |
| Catégorisation rétroactive massive automatique | "Nettoyer l'historique" | Réécrit l'historique sans trace claire, change les budgets et dettes (F10) | Proposition en lot via écran de triage, validation humaine |

---

## Surface MCP (outils, ressources, prompts)

Principe : **peu d'outils, étroits, lecture et écriture séparées, annotés**. Les serveurs MCP communautaires pour Actual Budget exposent 60 à 85 outils, d'autres des modes lecture seule par drapeau d'environnement. Pour un foyer, viser **25 à 35 outils** visibles du modèle, regroupés par intention. Chaque outil porte un `title` et `readOnlyHint` ou `destructiveHint` (exigence des annuaires Anthropic, et ces indices déterminent les permissions automatiques de Claude : un outil en lecture seule s'exécute sans confirmation, un outil destructif demande toujours confirmation).

### Outils de lecture (tous `readOnlyHint: true`, renvoient `structuredContent` + `content` texte)

| Outil | Rôle | Complexité |
|-------|------|------------|
| `get_household_context` | Membre courant, rôle, foyer, devise, comptes accessibles, catégories (arbre), politique d'écriture effective, date | LOW |
| `get_dashboard` | Agrégat unique pour le tableau de bord : soldes, budgets, dettes nettes, épargne, alertes, dernières transactions, `as_of` | MEDIUM |
| `list_transactions` / `search_transactions` | Paginé, filtrable, taille bornée | MEDIUM |
| `get_balances` | Réel / prévisionnel / projeté par compte | LOW |
| `get_budget_status` | Consommation, restant, statut, alertes par budget/période | MEDIUM |
| `get_debts_overview`, `get_settlement_plan`, `list_settlements` | Soldes nets, plan de règlement suggéré, historique | MEDIUM |
| `get_savings_overview` | Objectifs, allocations, projection | MEDIUM |
| `get_import_preview`, `get_import_triage`, `list_reconciliation_suggestions` | Écrans d'import : lecture seule, sans effet | MEDIUM |
| `analyze_spending`, `explain_budget_overrun`, `explain_debt`, `compare_periods`, `simulate_savings`, `simulate_budget_change` | Analyse et dry-run ; sorties structurées avec références aux transactions | MEDIUM |
| `list_pending_actions`, `get_audit_log` | Actions en attente et historique des actions de l'agent pour le membre | LOW |
| `get_bank_consent_status` | Fin de validité du consentement DSP2 | LOW |

### Outils d'écriture (séparés par action, jamais un `api_request`)

| Outil | Risque (classe) | Annotation | Notes |
|-------|----------------|------------|-------|
| `create_transaction`, `create_transactions_batch` | R1, réversible par `void` | `destructiveHint: false` | Idempotence obligatoire |
| `update_transaction_metadata` (catégorie, tags, description, override) | R1 ; `category_id` peut re-matérialiser des dettes | `destructiveHint: false` | Dry-run de l'effet sur dettes |
| `void_transaction`, `correct_transaction` | R2 | `destructiveHint: true` | Prompt Claude natif systématique |
| `confirm_transaction` (draft → confirmed) | R1 | | Fige l'aggregate |
| `create_share_request`, `set_share_ratio`, `set_debt_override` | R2 : engagent un autre membre | | Sous politique |
| `create_settlement` | R2 | `destructiveHint: true` | Aperçu des lignes d'apurement |
| `create/update/archive_budget` | R2 : reclassement F10 rétroactif | `destructiveHint: true` | `simulate_budget_change` d'abord |
| `create/move/archive_category` | R1 / R2 | | |
| `import_commit` | R2 | `destructiveHint: true` | Fichier jamais dans le contexte du modèle |
| `confirm_reconciliation`, `reject_reconciliation`, `unreconcile` | R1, **plancher : jamais `direct` pour confirm** | | Pas d'auto-confirm |
| `create/update_savings_goal`, `set_goal_allocations` | R1 | | |
| `confirm_pending_action`, `reject_pending_action`, `modify_then_confirm` | Canal de confirmation | `destructiveHint: true` | Voir politique |
| `set_write_policy` (soi-même uniquement) | R3 : durcir est libre, **assouplir exige un pas-à-pas** | `destructiveHint: true` | Jamais modifiable pour un autre membre |
| `invite_member`, `revoke_member`, `promote_admin` | R3 (admin) | `destructiveHint: true` | Jamais en `direct` |

### Ressources et prompts

| Élément | Contenu | Confiance |
|---------|---------|-----------|
| Prompts MCP : `saisir_depense`, `point_mensuel`, `pourquoi_depassement`, `regler_les_dettes`, `trier_import` | Gabarits de conversation. Claude documente le support des prompts et ressources pour les serveurs distants (article d'aide Anthropic, possiblement ancien) | MEDIUM |
| Ressource `prosperity://glossary` | Vocabulaire métier (Compte commun, Quote-part, Pointage…) pour que Claude emploie les bons termes | MEDIUM |
| Ressources gabarits d'artefacts (`prosperity://artifacts/dashboard`, `…/entry-form`, `…/import-triage`, `…/pending-actions`) | HTML complet à publier tel quel | MEDIUM |
| `instructions` du serveur à l'initialisation | Règles d'usage (toujours passer par les outils d'agrégat, ne jamais calculer, demander confirmation sur ambiguïté) | MEDIUM : à vérifier que claude.ai l'expose au modèle |
| **Ne pas compter sur les ressources pour le contexte critique** | Dans claude.ai, les ressources sont plutôt attachées par l'utilisateur ; le modèle ne les lit pas forcément de lui-même | Mettre l'essentiel dans les descriptions d'outils et dans `get_household_context` |

### Règles de conception des réponses

- `structuredContent` stable et versionné (`schema_version`), avec `as_of` et montants en centimes entiers **et** formatés ; `content` texte court pour les clients sans rendu.
- Taille de réponse bornée, pagination ; ne jamais renvoyer un dump (critère de revue Anthropic).
- Descriptions d'outils factuelles : décrire ce que l'outil fait, jamais "dis à l'utilisateur de…" (les descriptions qui dictent un comportement à Claude sont rejetées en revue).
- **Données importées = non fiables.** Libellés bancaires, memos et descriptions peuvent contenir des instructions. Les renvoyer dans un champ clairement typé `untrusted_text`, et ne jamais laisser un champ issu d'un import déclencher une écriture sans confirmation.

---

## Politique d'écriture (par membre et par type d'action)

### Modèle

| Mode | Comportement | Quand |
|------|--------------|-------|
| `direct` | L'outil écrit immédiatement via les services métier | Actions réversibles, faible enjeu |
| `propose` | L'outil crée une **PendingAction** (immuable, avec aperçu d'effet calculé serveur), ne mute rien ; l'écriture a lieu à la confirmation | Actions engageantes ou irréversibles |
| `risk_based` | Évalué par une règle serveur déterministe : classe de l'action, montant au-dessus d'un seuil, nouveauté (catégorie/bénéficiaire jamais vu), origine du texte (issu d'un import), nombre d'écritures récentes | Défaut raisonnable pour les actions de classe R1 |

La politique est une **matrice membre × type d'action** (≈ 8 types : saisie, métadonnées, void/correction, partage/dette, règlement, budget/catégorie, import, épargne), avec un défaut de foyer et un défaut sûr par classe de risque.

### Classes de risque et planchers

| Classe | Exemples | Plafond d'assouplissement |
|--------|----------|--------------------------|
| R0 (lecture) | tout outil `readOnlyHint` | Toujours libre |
| R1 (réversible, périmètre perso) | saisie, métadonnées, objectifs d'épargne | `direct` autorisé |
| R2 (engage un autre membre ou réécrit des dérivés) | demande de partage, règlement, budget (F10), void, import commit | `direct` autorisé par le membre concerné, défaut `propose` |
| R3 (identité, droits, politique) | rôles, invitation, **assouplissement** de la politique | Toujours `propose` avec confirmation hors-bande, non configurable |
| Planchers absolus | `confirm_reconciliation`, auto-confirm, lien de compte bancaire, accès à un compte non accessible | Jamais `direct` |

### Le canal de confirmation (décision structurante)

Le modèle ne doit pas pouvoir confirmer ce qu'il propose. Options, dans l'ordre de robustesse :

1. **MCP Apps, outils `visibility: ["app"]`** : `confirm_pending_action` n'apparaît pas dans la liste d'outils du modèle et n'est appelable que depuis la vue, donc par un clic humain. Seule solution où le serveur peut garantir la séparation. HIGH sur la spec ; l'état de rendu dans claude.ai est instable en novembre 2026 (voir ci-dessous).
2. **`destructiveHint: true` sur les outils de confirmation** : Claude documente que les outils destructifs demandent toujours confirmation de l'humain avant exécution. La confirmation devient un prompt natif de l'interface Claude, hors de portée du modèle. MEDIUM : comportement documenté pour la revue d'annuaire, à valider en pratique sur un connecteur personnalisé (permissions par outil "Always allow / Needs approval / Blocked" modifiables par l'utilisateur : un utilisateur peut les passer en "Always allow", ce que le serveur ne peut pas empêcher).
3. **Pas-à-pas serveur** pour les actions R3 : code à usage unique affiché sur l'écran OAuth du serveur (seule page web tolérée), pas dans la conversation.
4. Confirmation dans la conversation ("oui, valide") : **insuffisant seul**, car injectable. À accepter uniquement pour R1 sous `risk_based`.

Conséquence de conception : le serveur doit rester sûr **même si** l'utilisateur met tous les outils en "Always allow". D'où : planchers côté serveur, aperçu d'effet dans la PendingAction, expiration des actions en attente (TTL), et liaison de la confirmation à l'identité authentifiée (un membre ne confirme que ses propres actions).

### Fonctions associées

| Feature | Complexity | Notes |
|---------|------------|-------|
| PendingAction : état `pending → confirmed / rejected / expired / superseded`, lignée `derived_from`/`superseded_by`, squelette d'audit conservé après purge du payload [M] | MEDIUM | Reprendre ADR 0004 tel quel |
| `modify_then_confirm` : l'originale passe en `superseded`, la dérivée est créée [M] | MEDIUM | |
| Aperçu d'effet calculé serveur (dette générée, budget consommé) avant confirmation [N] | MEDIUM | Dry-run des calculateurs |
| TTL et purge du payload des actions non confirmées [N] | LOW | |
| Assouplissement de politique en deux temps, durcissement immédiat [N] | MEDIUM | Évite qu'une injection ne désactive la protection |
| Limitation de débit par membre/session (plafond d'écritures par heure) et circuit-breaker "trop d'écritures" qui bascule temporairement en `propose` [N] | MEDIUM | Reprend les heuristiques de compromission de l'ADR 0004 |

---

## Journal d'audit des actions de l'agent

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Entrée immuable par appel d'écriture : membre, horodatage, outil, hash des entrées, décision de politique (direct/pending/refusé), résultat, identifiant d'entité créée, clé d'idempotence, lignée de PendingAction [M→N] | Répond à "qu'a fait Claude en mon nom ?" ; prérequis de confiance du mode `direct` | MEDIUM | Squelette conservé après purge des données sensibles |
| Provenance de l'appel : `clientInfo` MCP, jeton, marqueur "origine : texte issu d'import" [N] | Distinguer conversation, artefact, autre client | MEDIUM | Le serveur ne sait pas si un appel vient d'un clic ou d'une décision du modèle quand le même outil est appelé des deux façons : ne pas promettre cette distinction hors outils `visibility: ["app"]` |
| Lecture par le membre de **son** journal, filtrable, dans un écran dédié [N] | Transparence | LOW | Un membre ne voit jamais les entrées d'un compte perso d'un autre |
| Audit des opérations admin (invitation, promotion, révocation) [M] | Déjà prévu (ADR E04) | LOW | |
| Annuler par lot "tout ce que Claude a fait dans cette session" (`void` en cascade, avec liste) [N] | Filet de sécurité après une session qui dérape | MEDIUM | Possible grâce à l'immutabilité ; sous politique `propose` |

---

## Artefacts vs MCP Apps : ce qui est vérifié

### Artefacts claude.ai avec capacité `mcp` (chemin retenu par PROJECT.md)

| Fait | Statut | Source / confiance |
|------|--------|--------------------|
| Une page publiée peut appeler les connecteurs claude.ai **du lecteur**, avec ses identifiants ; le code de la page ne voit jamais de jeton | Vérifié | Doc officielle Claude Code ("Pull live data with MCP connectors") + définitions de types runtime 0.2.98. HIGH |
| Chaque lecteur est invité à consentir avant le premier appel ; un lecteur qui refuse voit la page sans ses sections live ; le refus dure le temps du chargement | Vérifié | Doc officielle. HIGH |
| Manifeste `capabilities: {mcp: {servers: [{server, tools}]}}` ; `server` = **nom d'affichage** du connecteur ; `tools` obligatoire et non vide (jamais "tous") | Vérifié | Runtime 0.2.98. HIGH. Un outil absent du manifeste rejette `not_in_manifest` |
| `watchTool(server, tool, input, handler, {cache, refetchInterval})` pour l'affichage : rejoue le cache, rafraîchit, polling à plancher ~30 s, pause onglet masqué, 64 watches max par vue, **outils en lecture seule uniquement** | Vérifié | Runtime 0.2.98 (`mcp.d.ts`). Les noms `watchTool`/`callTool` n'apparaissent **pas** dans la doc publique consultée : ils viennent des types livrés avec le runtime. MEDIUM sur la stabilité du nom, mais le contrat est versionné et épinglé par artefact (`contract`) |
| `callTool(server, tool, input, options)` pour les actions : une fois, sur geste ; échec = rejet `tool_error` ; **rejet ambigu sur écriture (`server_unavailable`, `upstream_error`) ≠ preuve d'absence d'exécution** | Vérifié | Runtime 0.2.98. HIGH |
| Codes d'erreur fermés (`needs_reauth`, `server_not_connected`, `approval_required`, `blocked_by_policy`, `selection_required`…) : l'UX doit brancher par code | Vérifié | Runtime 0.2.98. HIGH |
| Résultats mis en cache dans le navigateur du lecteur, par lecteur + artefact ; outils déclarés `readOnlyHint: true` mis en cache par défaut | Vérifié | Doc officielle + runtime. HIGH. **Données financières en cache navigateur : le noter dans le modèle de menace** |
| Argument fichier dans `callTool` : leaf `{$file: {data, name, type}}`, jusqu'à 16 Mio, hors limite d'entrée de 1 Mio ; à tester via `listTools().fileArgs` | Vérifié | Runtime 0.2.98. HIGH. Ouvre l'import de relevé sans passer par le contexte du modèle |
| `describeTool` pour lire le schéma d'un outil à l'exécution ; `listTools` pour adapter l'UI | Vérifié | Runtime 0.2.98 |
| Disponibilité : plans Pro, Max, Ultra, Team, Enterprise ; **pas de lecteur anonyme** (lien public sans connexion = sections live absentes) ; interrupteur organisation "Enable artifact connectors" ; seuls les connecteurs claude.ai sont appelables, pas les serveurs MCP locaux (sauf `host:` dans l'app desktop, propriétaire seulement) | Vérifié | Doc officielle. HIGH. **Pas de plan Free** : chaque membre du foyer doit avoir un plan payant |
| Un artefact est une page statique, ≤ 16 Mio, CSP stricte (pas de `fetch` hors origine ; scripts depuis 5 CDN) ; les appels connecteur passent par claude.ai | Vérifié | Doc officielle. HIGH |
| Un artefact publié par un membre peut être modifié par un éditeur ; il est partageable dans l'organisation | Vérifié | Doc officielle. Implications de gouvernance si l'artefact porte des écritures : un éditeur peut changer ce que fait le bouton |

### MCP Apps (UI fournie par le serveur)

| Fait | Statut | Source / confiance |
|------|--------|--------------------|
| Extension officielle (SEP-1865), spécification stable datée 2026-01-26 ; ressources `ui://` ; `_meta.ui.resourceUri` sur l'outil ; MIME `text/html;profile=mcp-app` | Vérifié | modelcontextprotocol.io. HIGH |
| Rendu en iframe sandboxée ; communication JSON-RPC par `postMessage` ; la vue peut appeler `tools/call` sur **son** serveur, envoyer `ui/message` (au chat), `ui/update-model-context`, demander `fullscreen`/`pip` | Vérifié | Spec. HIGH |
| **Outils `visibility: ["app"]`** : cachés de la liste d'outils du modèle, appelables seulement depuis la vue ; l'hôte DOIT rejeter l'appel d'un outil sans `"app"` | Vérifié | Spec. HIGH. C'est le seul mécanisme public qui sépare "clic humain" de "décision du modèle" |
| Supporté par claude.ai web et Claude Desktop (annonce du 26 janvier 2026), plans Free à Enterprise ; un connecteur personnalisé s'ajoute par URL pour tester | Vérifié | Docs Anthropic. HIGH sur le support ; **MEDIUM sur le rendu des connecteurs personnalisés** : un ticket ouvert au 20 novembre 2026 (ext-apps #671) rapporte des UI non rendues sur claude.ai/Desktop, sans correctif officiel, avec des contournements (bundler le SDK inline, implémenter `ping`, envoyer `initialized` sans attendre, déclarer l'extension à `initialize`, `ui.domain` calculé par SHA-256 de l'URL du serveur) |
| Page d'aide Anthropic : les interactions "achats et transactions financières" dans les vues de chat ne sont pas prises en charge ; les connecteurs qui **transfèrent de l'argent** sont exclus des annuaires | Vérifié | support.claude.com + critères de revue. **MEDIUM** : visent l'annuaire/les paiements ; Prosperity n'effectue aucun mouvement d'argent et n'est pas destiné à l'annuaire, mais à surveiller (un règlement "virement" est un enregistrement comptable) |
| Mobile : la page d'aide dit à la fois "tous les utilisateurs sur iOS/Android" et "pas encore sur Claude Mobile" ; incohérent | Non résolu | LOW. À tester sur appareil réel |
| Entry points, sites embarqués : réservés aux listings Verified de l'annuaire ; app tools et side panel soumis à l'accès de l'organisation | Vérifié | Docs Anthropic. Non utilisable pour un connecteur privé |

### Recommandation

1. **v1 : artefacts `mcp`** pour dashboard, saisie et triage (chemin le plus stable, vérifié sur le contrat 0.2.98, partage au foyer, `$file` pour l'import). Concevoir les outils UI-agnostiques.
2. **Spike MCP Apps en parallèle, limité à l'écran d'actions en attente** : c'est là que `visibility: ["app"]` apporte une garantie de sécurité que rien d'autre ne donne. Si le rendu est fiable sur le connecteur personnalisé, migrer la confirmation dessus ; sinon rester sur `destructiveHint` + planchers serveur.
3. **Attention au double rendu** : ajouter `_meta.ui.resourceUri` à un outil fait rendre une vue dans la conversation dès que Claude l'appelle, ce qui peut doubler l'artefact. Ne l'ajouter qu'aux outils de l'écran de confirmation.
4. Un même outil de lecture renvoie `structuredContent` ; il sert `watchTool` (artefact) et `ontoolresult` (MCP Apps) sans changement.

---

## Import et fichiers : point de faisabilité

Un relevé OFX/CSV ne peut pas raisonnablement transiter par le contexte du modèle. Chemins possibles :

| Chemin | Verdict |
|--------|---------|
| Artefact avec zone de dépôt, `callTool` avec argument `$file` (≤ 16 Mio, hors limite d'entrée de 1 Mio) | **Retenu**, sous réserve que `listTools().fileArgs` soit vrai pour le lecteur ; sinon base64 inline sous 1 Mio, ou refuser. Le serveur parse, déduplique, renvoie le résumé |
| Claude lit la pièce jointe et appelle un outil avec le contenu en paramètre | Acceptable pour de très petits fichiers seulement (coût en tokens, troncature, injection par libellés) |
| Lien de dépôt temporaire hébergé par le serveur (URL signée) | Possible mais ajoute une surface web hors OAuth, contraire à la contrainte "pas d'UI web" ; à écarter en v1 |
| Agrégation DSP2 | Évite le fichier ; mais consentement SCA à renouveler (90/180 j) avec redirection navigateur vers la banque, à lancer depuis un lien |

---

## Feature Dependencies

```
Connecteur MCP distant + OAuth (identité par membre)
    └──requires──> Foyer / membres / rôles
                       └──requires──> Comptes (perso/commun, quotes-parts)
                                          └──requires──> Catégories
                                                             └──requires──> Transactions (splits, états, immutabilité)
                                                                                └──requires──> Idempotence des écritures

Transactions ──requires──> Saisie via Claude (create_transaction, résolution par nom)
Transactions ──enhances──> Récurrences (planned) ──enhances──> Solde projeté, projection épargne

Budgets ──requires──> Catégories + Transactions
Dettes (F10 overflow) ──requires──> Budgets + Comptes communs + Transactions
Dettes (share_request) ──requires──> Comptes perso + Transactions
Règlements ──requires──> Dettes
Règlements ──enhances──> Pointage (virement interne rapproché de la ligne bancaire)

Import (OFX/CSV) ──requires──> Comptes + Transactions (draft) + Dédup + argument $file
Pointage ──requires──> Import + Transactions + MatchScorer + normalize_label (partagé avec dédup)
DSP2 ──requires──> Import (modèle BankTransaction commun) + job de polling + consentement
Triage assisté par Claude ──requires──> Import + Catégories (+ mémoire libellé→catégorie en option)

Épargne ──requires──> Comptes + Transactions (split.savings_goal_id)
Projection ──requires──> historique 30-90 j (+ Récurrences pour le fallback de planifié)

Politique d'écriture ──requires──> PendingAction + Audit + classes de risque des outils
PendingAction ──requires──> Aperçu d'effet (dry-run des calculateurs de dettes/budgets)
Confirmation sûre ──requires──> (MCP Apps app-only) OU (destructiveHint + planchers serveur)
Écran d'actions en attente ──requires──> PendingAction

Artefacts (dashboard) ──requires──> Outils de lecture agrégés (readOnlyHint) + mêmes noms de connecteur chez tous les membres
Artefacts (saisie/triage/règlement) ──requires──> Outils d'écriture + idempotence + politique d'écriture
Analyse ──requires──> Transactions + Budgets + Dettes (lecture)
Prompts / gabarits d'artefacts ──enhances──> Artefacts

Auto-confirm du pointage ──conflicts──> Pointage user-in-the-loop (décision actée)
Outil générique run_sql/api_request ──conflicts──> Cloisonnement, audit, critères de revue Anthropic
Données financières dans la db de l'artefact ──conflicts──> Exactitude et cloisonnement côté backend
```

### Dependency Notes

- **Idempotence requise avant toute écriture exposée** : le contrat runtime des artefacts rend les retries ambigus. La clé d'idempotence est un prérequis de `create_transaction`, pas un ajout tardif.
- **Politique d'écriture requiert l'audit et la PendingAction, pas l'inverse** : on peut livrer `direct` seul + audit en v1, mais pas `propose` sans PendingAction ni son écran.
- **Reclassement F10 requiert un dry-run avant d'autoriser `direct` sur les budgets** : sinon un agent réécrit des dettes passées sans aperçu.
- **Triage requiert `$file`** : si `fileArgs` est indisponible sur la surface du lecteur, l'import est dégradé (petits fichiers inline). À tester tôt (spike).
- **Dashboard partagé requiert un nom de connecteur identique chez tous les membres** : documentation d'onboarding obligatoire.
- **DSP2 est indépendant du fichier** mais réutilise le modèle `BankTransaction`, la dédup et le pointage : à placer après l'import fichier.
- **Récurrences** : dépendance cachée du solde projeté et de la projection d'épargne ; absentes de PROJECT.md Active alors que présentes dans l'ancien domaine.

---

## MVP Definition

### Launch With (v1)

- [ ] Connecteur MCP distant + OAuth + identité par membre — prérequis de tout
- [ ] Foyer, rôles, bootstrap, invitations, cloisonnement strict (tests de propriété) — confiance
- [ ] Comptes, quotes-parts, catégories hiérarchiques — base
- [ ] Transactions à splits, états, immutabilité, `void` — coeur du modèle
- [ ] Idempotence + erreurs typées sur toutes les écritures — sécurité des retries
- [ ] Saisie conversationnelle (`create_transaction`, résolution par nom, `void` de la dernière saisie) — Core Value
- [ ] `get_household_context` + `get_dashboard` + `get_balances` + `list/search_transactions` — Core Value "voir"
- [ ] Budgets + consommation + alertes lues à l'ouverture / en réponse d'écriture — table stakes
- [ ] Dettes (overflow F10 + share_request) + vue nette + règlement multi-lignes + masquage débiteur — différenciateur central
- [ ] Politique d'écriture : `direct` et `propose` par membre × type d'action, PendingAction, planchers, audit consultable — différenciateur nouveau et condition de confiance
- [ ] Artefacts dashboard + formulaire de saisie + écran d'actions en attente — interfaces de la Core Value
- [ ] Import OFX + dédup + triage (dépôt `$file`) + pointage avec confirmation humaine — usage cible
- [ ] Outils d'analyse de base (`analyze_spending`, `explain_budget_overrun`) — usage cible "pourquoi ?"

### Add After Validation (v1.x)

- [ ] Mode `risk_based` complet (seuils, nouveauté, origine import) — après avoir observé les usages réels de `direct`/`propose`
- [ ] Récurrences et solde projeté — dès que le besoin de prévisionnel se fait sentir
- [ ] Épargne (objectifs, allocations, projection 90 j) + écran dédié — domaine déjà modélisé, moindre urgence
- [ ] Import CSV avec mapping de colonnes — OFX d'abord
- [ ] Triage assisté avec mémoire libellé→catégorie — après un volume d'imports suffisant
- [ ] Revue mensuelle (`point_mensuel`), détection d'abonnements et d'anomalies
- [ ] Double accord sur les règlements — si le besoin apparaît dans l'usage
- [ ] Annulation par lot d'une session de l'agent
- [ ] Photo de ticket → transaction — dépend de la saisie mais peu coûteux

### Future Consideration (v2+)

- [ ] Agrégation DSP2 (Enable Banking/GoCardless) — fort coût (polling, consentement SCA, renouvellement), valeur après que l'import fichier est solide
- [ ] Migration de la confirmation vers MCP Apps `visibility: ["app"]` — si le rendu sur connecteur personnalisé devient fiable
- [ ] Notifications hors Claude (email) — seulement si les alertes lues à l'ouverture se révèlent insuffisantes
- [ ] Multi-devise en usage, multi-foyers — hors périmètre acté

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Connecteur MCP + OAuth + identité par membre | HIGH | HIGH | P1 |
| Cloisonnement strict + masquage débiteur | HIGH | MEDIUM | P1 |
| Transactions à splits immuables + `void` | HIGH | HIGH | P1 |
| Idempotence + erreurs typées | HIGH | MEDIUM | P1 |
| Saisie conversationnelle | HIGH | MEDIUM | P1 |
| Outils de lecture agrégés + dashboard artefact | HIGH | MEDIUM | P1 |
| Budgets + alertes lues | HIGH | MEDIUM | P1 |
| Dettes F10 + règlements multi-lignes | HIGH | HIGH | P1 |
| Politique d'écriture `direct`/`propose` + PendingAction + audit | HIGH | HIGH | P1 |
| Import OFX + triage + pointage | HIGH | HIGH | P1 |
| Analyse "pourquoi ?" | HIGH | MEDIUM | P1 |
| Formulaire de saisie artefact | MEDIUM | MEDIUM | P1 |
| Mode `risk_based` | MEDIUM | MEDIUM | P2 |
| Épargne + projection | MEDIUM | MEDIUM | P2 |
| Récurrences / solde projeté | MEDIUM | MEDIUM | P2 |
| Import CSV | MEDIUM | MEDIUM | P2 |
| Photo de ticket | MEDIUM | LOW | P2 |
| Revue mensuelle, anomalies | MEDIUM | MEDIUM | P2 |
| Triage assisté + mémoire | MEDIUM | MEDIUM | P2 |
| DSP2 | HIGH | HIGH | P3 |
| MCP Apps pour confirmation | MEDIUM | MEDIUM | P3 (spike en P2) |
| Notifications email | LOW | MEDIUM | P3 |

**Priority key :** P1 = indispensable au lancement, P2 = à ajouter après validation, P3 = reporter.

## Competitor Feature Analysis

> Analyse de mémoire (MEDIUM), non re-vérifiée en ligne sauf mention. Les recherches de cette session ont confirmé : Splitwise Pro réserve scan de tickets, récurrences et graphiques ; Tricount est gratuit et joint la photo sans OCR ; plusieurs serveurs MCP communautaires existent pour Actual Budget et YNAB, avec lecture seule par défaut ou par drapeau.

| Feature | Splitwise / Tricount | YNAB / Actual Budget | Firefly III | Finary / Bankin' / Linxo | Notre approche |
|---------|----------------------|----------------------|-------------|---------------------------|----------------|
| Partage de dépenses et "qui doit quoi" | Coeur du produit, partage égal/exact/%/parts, règlement | Non | Non (pas de dettes entre membres) | Non | Dettes projetées côté serveur, issues du budget (F10) et des demandes de partage |
| Budget | Non | Enveloppes zero-based (YNAB), enveloppes ou suivi (Actual) | Budgets + auto-budget | Budgets par catégorie, alertes | Plafond par catégorie/période, scope perso/commun, source de dette |
| Comptes perso étanches dans un foyer | Non | Partage de budget global | Multi-utilisateurs limité | Non | Cloisonnement dur, admin exclu |
| Double-entrée | Non | Actual : partiel | Oui | Non | Splits zero-sum immuables |
| Import fichier | Non | OFX/QIF/CSV | CSV via importer, OFX | Agrégation DSP2 | OFX puis CSV, DSP2 plus tard |
| Agrégation bancaire | Non | Actual : GoCardless/SimpleFIN ; YNAB : selon pays | Via importer | Coeur du produit (Bankin', Linxo, Finary) | v2 |
| Rapprochement / pointage | Non | Reconcile (YNAB, Actual) | Via règles | Non | Suggestions + confirmation humaine, jamais auto |
| Catégorisation automatique | Non | Actual : règles ; YNAB : mémoire de bénéficiaire | Règles et déclencheurs | Auto par commerçant | Suggestion Claude + mémoire libellé→catégorie |
| Récurrences | Pro (Splitwise) | Oui | Oui | Détection des échéances | Règles serveur, v1.x |
| Objectifs d'épargne | Non | Targets (YNAB) | Piggy banks | Objectifs (Bankin', Linxo) ; Finary : patrimoine | Allocations multi-comptes + projection 90 j |
| Patrimoine / investissements | Non | Non | Limité | Finary : coeur | Hors périmètre |
| Interface | App mobile/web | App | Web | App | **Claude uniquement** |
| Agent / IA | Scan de tickets (Pro) | Serveurs MCP communautaires, lecture seule par défaut | Non | Non | MCP natif, politique d'écriture par membre, audit, PendingAction |
| Politique d'écriture d'un agent | Sans objet | Drapeau global lecture seule / écriture | Sans objet | Sans objet | **Matrice par membre × type d'action, avec planchers et confirmation hors du modèle** |

## Sources

- Docs officielles Claude Code, "Share session output as artifacts", section "Pull live data with MCP connectors" (consentement par lecteur, comptes du lecteur, plans, pas de lecteur anonyme, interrupteur d'organisation, cache navigateur, contraintes de page) : https://code.claude.com/docs/en/artifacts — HIGH
- Notes de version Claude Code, semaine 29 (13-17 juillet 2026), artefacts appelant les connecteurs MCP : https://code.claude.com/docs/en/whats-new/2026-w29 — HIGH
- Définitions de types du runtime des artefacts, contrat 0.2.98 (`mcp.d.ts` : `watchTool`, `callTool`, `listTools`, `describeTool`, `invalidate`, codes d'erreur, `$file`, cache) : livrées avec le skill `artifact-capabilities` de cette session — HIGH pour le contrat, MEDIUM car les noms d'API ne figurent pas dans la doc publique consultée
- MCP Apps, vue d'ensemble : https://modelcontextprotocol.io/extensions/apps/overview.md — HIGH
- MCP Apps, spécification stable 2026-01-26 (`_meta.ui`, `visibility`, `ui/message`, `ui/update-model-context`, CSP, modes d'affichage) : https://raw.githubusercontent.com/modelcontextprotocol/ext-apps/main/specification/2026-01-26/apps.mdx — HIGH
- Annonce Anthropic, connecteurs interactifs (26 janvier 2026) : https://claude.com/blog/interactive-tools-in-claude — HIGH
- Aide Claude, utiliser les connecteurs interactifs (limite "achats et transactions financières", contrôles par outil) : https://support.claude.com/en/articles/13454812-using-interactive-connectors-in-claude — MEDIUM (incohérence sur le mobile)
- Docs Claude, démarrer avec MCP Apps (`ui.domain`, app tools, entry points réservés aux Verified) : https://claude.com/docs/connectors/building/mcp-apps/getting-started.md — HIGH
- Docs Claude, quickstart MCP Apps (`registerAppTool`, `registerAppResource`, test en connecteur personnalisé) : https://claude.com/docs/connectors/building/mcp-apps/quickstart.md — HIGH
- Docs Claude, critères de revue (outils lecture/écriture séparés, `readOnlyHint`/`destructiveHint` déterminent les permissions automatiques, pas de transfert d'argent, descriptions sans consignes comportementales) : https://claude.com/docs/connectors/building/review-criteria.md — HIGH
- Docs Claude, soumission d'un connecteur (OAuth 2.0, annotations obligatoires) : https://claude.com/docs/connectors/building/submission.md — HIGH
- Docs Claude, démarrer avec les connecteurs (permissions par outil Always allow / Needs approval / Blocked) : https://claude.com/docs/connectors/overview.md — HIGH
- Ticket ext-apps #671, MCP Apps non rendues sur claude.ai/Desktop (ouvert, dernier commentaire du 20 novembre 2026) : https://github.com/modelcontextprotocol/ext-apps/issues/671 — MEDIUM (rapport communautaire, pas de correctif officiel)
- Demande d'elicitation dans claude.ai (non confirmé comme supporté) : https://github.com/anthropics/claude-ai-mcp/issues/153 — LOW ; ne pas dépendre d'`elicitation` pour la confirmation
- Serveurs MCP communautaires Actual Budget et YNAB (nombre d'outils, mode lecture seule par drapeau) : https://github.com/s-stefanov/actual-mcp-server et résultats de recherche listés ci-dessus — MEDIUM, non vérifiés individuellement
- Splitwise vs Tricount (Pro : scan, récurrences, graphiques) : https://tricount.com/splitwise-vs-tricount — LOW (page concurrentielle, partiale)
- Domaine métier : `origin/main:CONTEXT.md`, `origin/main:docs/adr/0001, 0002, 0004, 0011, 0013`, `origin/main:docs/roadmap/README.md` — HIGH (référence interne)
- Connaissance générale de YNAB, Actual Budget, Firefly III, Finary, Bankin', Linxo : non re-vérifiée en ligne dans cette session — MEDIUM

---
*Feature research for: finances partagées d'un foyer, interface Claude via connecteur MCP*
*Researched: 2026-11-21*
