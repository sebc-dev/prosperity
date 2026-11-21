# Roadmap: Prosperity

## Overview

Prosperity renaît en connecteur MCP distant pour Claude, sur une branche vierge. Le parcours commence par une quality gate déterministe qui garde le dépôt avant la première ligne de domaine (phase 1). Il prouve ensuite, avec deux comptes claude.ai réels, qu'un connecteur personnalisé joignable, conforme et qui identifie chaque membre fonctionne de bout en bout ; c'est la sortie obligatoire avant tout domaine (phase 2). Viennent ensuite des tranches verticales utilisables depuis Claude : comptes cloisonnés (3), saisie conversationnelle et soldes, c'est-à-dire la boucle du Core Value (4), politique d'écriture et confirmation hors modèle (5), budgets, épargne, récurrences et analyse (6), dettes F10, règlements et tableau de bord complet (7), import de relevés et pointage (8). L'agrégation DSP2 ferme le jalon en réutilisant la dédup et le pointage de l'import (9). À partir de la phase 2, chaque phase se termine sur un comportement qu'on peut constater en parlant à Claude ou dans un artefact.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Socle et quality gate** - Dépôt TypeScript gardé par `pnpm quality`, seul juge en CI, avant toute ligne de domaine
- [ ] **Phase 2: Connecteur Claude et identité du foyer** - Deux membres ajoutent le connecteur, s'authentifient par passkey et `whoami` renvoie à chacun sa propre identité (spike MCP Apps inclus)
- [ ] **Phase 3: Comptes cloisonnés et catégories** - Comptes perso et communs, quotes-parts, catégories, avec un cloisonnement prouvé par RLS et par la matrice de fuites
- [ ] **Phase 4: Saisie conversationnelle et soldes** - « J'ai payé 84 € de courses, partagé 50/50 » crée la transaction ; soldes exacts, recherche, formulaire artefact
- [ ] **Phase 5: Politique d'écriture et confirmation hors modèle** - Modes `direct` / `propose` / `risk_based`, actions en attente confirmées dans une MCP App, audit consultable
- [ ] **Phase 6: Budgets, épargne, récurrences et analyse** - Budgets avec alertes, objectifs d'épargne projetés, récurrences, « pourquoi on a dépassé ? »
- [ ] **Phase 7: Dettes, règlements et vue d'ensemble** - Dettes F10, partages, règlements à double accord, tableau de bord complet et revue mensuelle
- [ ] **Phase 8: Import de relevés et pointage** - Dépôt OFX/CSV, aperçu, dédup, triage assisté et pointage confirmé par l'humain
- [ ] **Phase 9: Agrégation bancaire DSP2** - Enable Banking synchronise les comptes par le même chemin de dédup et de pointage que l'import

## Phase Details

### Phase 1: Socle et quality gate
**Goal:** As a développeur du projet, I want to voir chaque PR jugée par une seule gate déterministe (`pnpm quality`), identique en local et en CI, qui bloque typage laxiste, violations d'architecture, failles de sécurité, tests faibles et contournements, so that aucune ligne de domaine écrite par un agent n'entre dans le dépôt sans avoir passé cette gate.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07, QUAL-08, QUAL-09
**Success Criteria** (what must be TRUE):
  1. `pnpm quality` rend le même verdict en pré-push et en CI et écrit `reports/gate.json` ; la protection de branche n'exige qu'un seul check, `quality`.
  2. Des PR de démonstration, une violation chacune, sont toutes rejetées par la CI : assertion `as`, `any`, fonction trop complexe, outil MCP qui importe `adapters/db`, cycle de modules, export mort, bloc dupliqué, secret en clair, SQL concaténé, handler sans `Principal`, action CI non épinglée.
  3. Sur un module canari, un test faible fait échouer la gate par le score de mutation Stryker et par la couverture du domaine pur sous 100 %. Un test d'intégration tourne contre un PostgreSQL 18 réel démarré par Testcontainers, en ordre aléatoire, avec la seed loguée.
  4. Sans approbation humaine explicite (commit d'approbation signé par une clé matérielle, D-14), la CI bloque une PR qui baisse un seuil, retire une assertion, ajoute une échappatoire (`@ts-ignore`, `.skip`, `vi.mock(`…) ou modifie un chemin protégé (`.github/**`, configuration de la gate, `deploy/**`). Les permissions de l'agent refusent l'édition de ces chemins.
  5. Une dépendance ajoutée sans approbation signée `deps-approved`, ou plus récente que l'âge minimal de publication, fait échouer l'installation ou la CI.
**Plans**: 4/14 plans executed

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Squelette ambulant : `pnpm quality` → check `workflow-lint` → `reports/gate.json` → pré-push → CI, rattachement d'historique et PR brouillon de bootstrap (vague 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02-PLAN.md — Approbation humaine des dépendances, typage strict, lint type-aware, format, seuils et globs uniques (vague 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 01-03-PLAN.md — Tests unitaires, canari `src/shared/money`, couverture 100 % du pur, mutation Stryker sur le diff (vague 3)
- [x] 01-04-PLAN.md — Sécurité : secrets, Semgrep du projet (décision Q4), CVE ≥ 7, zizmor, hadolint, lint de sécurité advisory (vague 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 01-05-PLAN.md — PostgreSQL 18 réel : rôles séparés migrations / app, migration forward-only, Testcontainers, méta-tests RLS (vague 4)
- [ ] 01-06-PLAN.md — Compteur d'échappatoires à cliquet, juge d'intégrité, chemins protégés, scripts de garde de l'agent (vague 4)
- [ ] 01-07-PLAN.md — Décision du type de clé matérielle, juge d'approbation par commit signé (D-14, `allowed_signers` lu dans la base, présence vérifiée), check `approvals` (vague 4)
- [ ] 01-08-PLAN.md — Garde des dépendances (`deps-approved` signé, existence et âge npm), juge hors PR `quality-verdict` qui publie le statut requis `quality` (vague 4)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 01-09-PLAN.md — Frontières d'architecture, code mort, duplication (vague 5)

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 01-10-PLAN.md — Auto-test de la gate : runner, check `selftest`, trois cas témoins (vague 6)

**Wave 7** *(blocked on Wave 6 completion)*
- [ ] 01-11-PLAN.md — Auto-test : cas du typage, du lint et de l'architecture (QUAL-02, QUAL-03) (vague 7)
- [ ] 01-12-PLAN.md — Auto-test : cas de sécurité, test faible, intégrité, base et dépendances (QUAL-04 à QUAL-09) (vague 7)

**Wave 8** *(blocked on Wave 7 completion)*
- [ ] 01-13-PLAN.md — Nightly, pré-commit, documentation et limites, outil D-07b, preuve CI complète (26 cas) et budgets (vague 8)

**Wave 9** *(blocked on Wave 8 completion)*
- [ ] 01-14-PLAN.md — Verrou : relecture D-01, deny et garde de l'agent (édition, écriture, signature et clés, fusion), enrôlement de la clé et `allowed_signers` par l'humain, étapes de confiance, juge hors PR et ruleset `quality`, PR réelles D-07b signées (vague 9)

### Phase 2: Connecteur Claude et identité du foyer
**Goal:** As a membre du foyer, I want to ajouter Prosperity comme connecteur personnalisé dans mon propre compte claude.ai et m'y authentifier par passkey, so that Claude agisse sous mon identité, sur une instance joignable et conforme, avant qu'existe la moindre donnée financière.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CONN-01, CONN-02, CONN-03, CONN-04, CONN-05, CONN-06, CONN-07, CONN-08, FOY-01, FOY-02, FOY-03, FOY-04, OPS-01, OPS-03, UI-09
**Success Criteria** (what must be TRUE):
  1. Le premier admin est créé avec le secret de bootstrap à usage unique, après quoi toute nouvelle tentative de bootstrap échoue. L'admin invite un second membre par email ; l'invité devient `member` en consommant l'invitation à sa première autorisation OAuth. Une invitation expirée, révoquée ou déjà consommée est refusée.
  2. Depuis deux comptes claude.ai distincts, chaque membre ajoute l'URL HTTPS publique et stable de l'instance (conteneur sur le homelab, exposé par tunnel) et se connecte par passkey. `get_household_context` lui renvoie sa propre identité, ses comptes accessibles, la devise EUR, ses préférences et sa politique d'écriture, jamais celles de l'autre membre.
  3. Un diagnostic lancé depuis Internet confirme les exigences claude.ai : `401` avec `resource_metadata` sur `POST /mcp` sans jeton ; Streamable HTTP sans état de session ; PRM et AS conformes ; A record IPv4 public ; aucune redirection inter-hôtes ; endpoints d'auth sous 10 s ; DCR refusé et tout client hors claude.ai/claude.com refusé ; seules les routes MCP, OAuth et `.well-known` publiques. Une sonde externe alerte quand le connecteur devient injoignable.
  4. Un admin révoque un membre ou en promeut un autre admin (acte séparé et audité). Le jeton du membre révoqué est rejeté dès l'appel suivant, et un jeton dont l'audience ne correspond pas à l'URL canonique est refusé. Le snapshot versionné de `tools/list`, relu par un humain, ne contient aucun argument d'identifiant de membre.
  5. Spike MCP Apps : une MCP App minimale servie par le connecteur s'affiche dans claude.ai pour les deux membres, et un outil `visibility: ["app"]` y est appelable sans apparaître dans la liste vue par le modèle. Si l'essai échoue, l'échec est constaté et le repli (page d'approbation hors bande) est consigné comme décision avant la phase 5.
**Plans**: TBD
**UI hint**: yes

### Phase 3: Comptes cloisonnés et catégories
**Goal:** As a membre du foyer, I want to créer et consulter depuis Claude mes comptes personnels et communs, avec leurs quotes-parts, ainsi que mes catégories, so that mes comptes personnels restent invisibles de tout autre membre, admin compris, avant que la première dépense soit saisie.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: FOY-05, FOY-06, CPT-01, CPT-03, CPT-04, OPS-02, TRX-11
**Success Criteria** (what must be TRUE):
  1. Depuis Claude, un membre crée un compte personnel, puis un compte commun avec un autre membre : quotes-parts en points de base, 50/50 par défaut, ou 60/40 si demandé. Les deux membres voient le compte commun ; seul le propriétaire voit le compte personnel.
  2. Quand un admin demande à Claude le compte personnel d'un autre membre, il obtient `not_found`, exactement la réponse d'un compte inexistant. En CI passent la matrice outil × rôle × classe de compte (au moins 3 membres, dont un admin) et le test méta « RLS actif sur toute table à `owner_member_id` ».
  3. Un membre crée une hiérarchie de catégories et la réorganise ; un déplacement qui créerait un cycle est refusé. Il archive et désarchive une catégorie, et aucun outil ne permet d'en supprimer une.
  4. Rejouer une création de compte ou de catégorie avec la même clé d'idempotence renvoie le résultat initial, sans doublon. Les montants sont stockés en centimes entiers ; toute devise autre qu'EUR est refusée.
  5. Une sauvegarde chiffrée part automatiquement hors machine, et un test automatisé la restaure avec succès sur une instance vierge.
**Plans**: TBD

### Phase 4: Saisie conversationnelle et soldes
**Goal:** As a membre du foyer, I want to saisir une dépense en une phrase à Claude ou dans un formulaire artefact, so that je voie aussitôt les soldes exacts de mes comptes, calculés par le serveur.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: TRX-01, TRX-02, TRX-03, TRX-04, TRX-05, TRX-06, TRX-10, TRX-12, CPT-02, UI-02, UI-07, UI-08
**Success Criteria** (what must be TRUE):
  1. « J'ai payé 84 € de courses sur le compte commun, partagé 50/50 » crée une transaction dont le serveur construit les splits, de somme nulle (contrôlée en domaine et en base). La réponse donne l'état résultant. Plusieurs dépenses dictées en une phrase renvoient un résultat par ligne, et une dépense future peut être saisie en `planned`.
  2. Un nom de compte, de catégorie ou de membre ambigu ou inconnu renvoie `needs_clarification` avec les candidats, et rien n'est écrit. Tout échec renvoie un code du vocabulaire fermé.
  3. Le montant et les splits d'une transaction `confirmed` ne peuvent pas être modifiés ; seuls la catégorie, les tags et la description restent éditables. Le membre corrige une saisie par `correct_transaction` (`void` puis nouvelle transaction) et peut annuler sa dernière saisie.
  4. Pour chaque compte, le membre voit le solde réel, le prévisionnel et le projeté fin de mois. Il retrouve ses transactions par période, compte, catégorie, montant, texte ou tag, avec une pagination par curseur et des réponses de taille bornée.
  5. Un artefact formulaire, chargé depuis un gabarit servi par le connecteur (ressource MCP), liste les vrais comptes et catégories du lecteur et crée la transaction au clic, avec une clé d'idempotence. Il affiche un état dégradé propre à chaque code d'erreur : connecteur absent, réauth, refus, données périmées. Ouvert par l'autre membre, il montre les données de cet autre membre.
**Plans**: TBD
**UI hint**: yes

### Phase 5: Politique d'écriture et confirmation hors modèle
**Goal:** As a membre du foyer, I want to choisir, type d'action par type d'action, ce que Claude écrit directement et ce qu'il doit me faire confirmer dans un écran que le modèle ne peut pas actionner, so that aucune écriture sensible ne se fasse en mon nom sans mon accord et que je puisse relire tout ce que Claude a fait.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: POL-01, POL-02, POL-03, POL-04, POL-05, POL-06, POL-07, TRX-07, TRX-08, UI-05
**Success Criteria** (what must be TRUE):
  1. Un membre règle, par type d'action, le mode `direct`, `propose` ou `risk_based`. En `propose`, une demande faite à Claude crée une action en attente au lieu d'écrire ; en `risk_based`, la décision dépend du montant et du type. Les planchers non configurables (pointage jamais `direct` ; identité, droits et politique toujours confirmés hors modèle) ne peuvent pas être assouplis.
  2. L'écran d'actions en attente liste les actions avec l'effet calculé par le serveur (dette générée, budget consommé) et permet de confirmer ou de refuser. C'est une MCP App, ou la page d'approbation hors bande si le spike de la phase 2 l'a décidé. Claude seul ne peut rien confirmer : les outils de confirmation n'apparaissent pas dans sa liste.
  3. Une action en attente expire à la fin de son TTL et passe en `superseded` quand elle est remplacée. À la confirmation, elle est revalidée : un payload altéré ou un état devenu incompatible est rejeté.
  4. Un membre annule plusieurs transactions en une seule action, selon sa politique. Une photo de ticket envoyée à Claude aboutit à une transaction multi-splits proposée avant toute écriture.
  5. Le membre consulte « ce que Claude a fait en mon nom » : qui, quoi, quand, mode, résultat. Au-delà du débit autorisé pour son grant OAuth, les écritures sont refusées avec un code explicite.
**Plans**: TBD
**UI hint**: yes

### Phase 6: Budgets, épargne, récurrences et analyse
**Goal:** As a membre du foyer, I want to fixer des budgets par catégorie, suivre des objectifs d'épargne, déclarer mes charges récurrentes et demander à Claude pourquoi un budget a dérapé, so that je pilote le mois avec des chiffres calculés par le serveur et non par Claude.
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: BUD-01, BUD-02, BUD-03, EPA-01, EPA-02, EPA-03, EPA-04, TRX-09, UI-06, ANA-01, ANA-02, ANA-04
**Success Criteria** (what must be TRUE):
  1. Un membre crée un budget mensuel par catégorie, perso ou commun, avec ses contributeurs ; le budget agrège les sous-catégories. Le membre voit sa consommation, son restant (jamais négatif) et son statut. Une saisie qui franchit 80 % ou 100 % renvoie l'alerte dans la réponse d'écriture.
  2. Un membre crée un objectif d'épargne adossé à un ou plusieurs comptes ; une sur-allocation donne un avertissement, pas une erreur. Il y rattache un versement et voit la projection sur 90 jours : masquée sous 30 jours, provisoire entre 30 et 90, avec l'état en avance, dans les temps ou en retard. `simulate_savings` répond à « combien par mois pour y arriver ? ».
  3. Un loyer déclaré récurrent est généré en `planned` par le job serveur, sans doublon même si le job tourne deux fois, et apparaît dans le solde projeté.
  4. « Pourquoi on a dépassé en restaurants ? » renvoie les contributeurs (plus grosses transactions, écart à la moyenne, pics, payeurs), que Claude raconte. L'analyse par catégorie, période, compte ou membre se compare à la période précédente. Les dépenses atypiques et les abonnements récurrents sont détectés.
  5. Les écrans budgets et épargne affichent consommation, alertes, objectifs et projections à partir des agrégats renvoyés par le connecteur.
**Plans**: TBD
**UI hint**: yes

### Phase 7: Dettes, règlements et vue d'ensemble
**Goal:** As a membre du foyer, I want to savoir qui doit combien à qui, comprendre chaque dette, la régler d'un commun accord et ouvrir un tableau de bord complet ainsi qu'une revue mensuelle, so that les comptes entre membres soient justes, explicables et soldables sans aucun calcul à la main.
**Mode:** mvp
**Depends on**: Phase 6
**Requirements**: DET-01, DET-02, DET-03, DET-04, DET-05, DET-06, DET-07, DET-08, DET-09, BUD-04, BUD-05, UI-04, UI-01, ANA-03
**Success Criteria** (what must be TRUE):
  1. Une dépense sur compte commun qui dépasse le budget couvrant génère une dette de quote-part sur l'excédent. La règle F10 s'applique : budget couvrant le plus spécifique, ordre `(date, id)`, montant entier quand aucun budget ne couvre la dépense. Une demande de partage depuis un compte personnel crée une dette sans que le débiteur voie la transaction ni le compte source. `share_ratio` et `debt_generation_override` modifient la dette en conséquence.
  2. Un membre voit le solde net et le détail par dette (montant − Σ lignes de règlement). `explain_debt` lui donne la chaîne causale d'une dette, masquage respecté, et le serveur lui suggère un plan de règlement.
  3. Un membre enregistre un règlement multi-dettes (virement interne, virement externe ou compensation virtuelle), avec nettage ligne à ligne. Le règlement ne devient effectif qu'après l'accord de l'autre membre.
  4. Modifier ou archiver un budget re-matérialise les dettes F10 de façon déterministe : chaque exécution donne le même résultat et laisse une trace d'audit. `simulate_budget_change` montre l'effet avant application, et le job `verify` prouve que la projection des dettes égale son recalcul.
  5. Le tableau de bord artefact lit au chargement, sans donnée incrustée, soldes, budgets, alertes, dettes, épargne et dernières transactions. L'écran dettes et règlements permet d'enregistrer un règlement, et le prompt `point_mensuel` produit la revue mensuelle du foyer.
**Plans**: TBD
**UI hint**: yes

### Phase 8: Import de relevés et pointage
**Goal:** As a membre du foyer, I want to déposer mon relevé bancaire OFX ou CSV, le trier dans un écran dédié et pointer mes transactions contre la banque, so that mes comptes reflètent la banque sans doublon ni ressaisie, et sans qu'un libellé importé puisse piloter Claude.
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: IMP-01, IMP-02, IMP-03, IMP-04, IMP-05, IMP-06, IMP-07, UI-03
**Success Criteria** (what must be TRUE):
  1. Dans l'écran de triage, un membre dépose un relevé OFX (1.x ou 2.x) ou un CSV de banque française. Le fichier arrive au serveur sans passer par le contexte du modèle. Avant commit, un aperçu (compteurs, doublons, plage de dates, anomalies) s'affiche, lié à un compte existant ; aucun compte n'est créé.
  2. Réimporter le même relevé ne crée aucun doublon, et les nouvelles lignes arrivent en `draft`.
  3. Le membre catégorise et partage les lignes, aidé de suggestions tirées de ses choix passés, puis valide en lot. Un libellé qui contient une instruction d'injection ne déclenche aucune écriture.
  4. Le serveur suggère des pointages transaction locale ↔ ligne bancaire, avec leur explication. Rien n'est pointé sans la confirmation du membre, et un dépointage ne ramène pas la transaction en `planned`.
**Plans**: TBD
**UI hint**: yes

### Phase 9: Agrégation bancaire DSP2
**Goal:** As a membre du foyer, I want to connecter mes comptes bancaires via Enable Banking, so that mes transactions arrivent seules, par le même chemin de dédup et de pointage que l'import fichier, avec la fraîcheur des données et l'expiration du consentement toujours visibles.
**Mode:** mvp
**Depends on**: Phase 8
**Requirements**: BNK-01, BNK-02, BNK-03, BNK-04, OPS-04
**Success Criteria** (what must be TRUE):
  1. Un membre connecte sa banque via Enable Banking, avec un consentement SCA lié à son identité. Aucun autre membre ne voit les comptes personnels ainsi connectés.
  2. Le job serveur synchronise les transactions dans les quotas (environ 4 lectures par jour et par banque). Aucun outil n'appelle l'agrégateur en synchrone.
  3. Une transaction reçue par DSP2 après avoir été importée par fichier n'est pas dupliquée, et elle entre dans le même flux de pointage.
  4. Les réponses concernées indiquent la date de dernière synchronisation et l'expiration du consentement. À J-14, le membre est prévenu, avec un lien de renouvellement.
  5. Les clés OAuth et Enable Banking sont hors git, et une rotation est jouée avec succès en suivant la procédure documentée.
**Plans**: TBD

## Spikes et recherche de phase

Ces points viennent de `.planning/research/SUMMARY.md` et sont à traiter au `/gsd-plan-phase` de la phase indiquée :

- Phase 1 : compatibilité de Stryker 10.1 avec Vitest 5.1 (bug #6004 : ne pas committer l'incrémental). Démarrer l'enregistrement de l'application Enable Banking et la collecte de relevés OFX/CSV anonymisés des banques du foyer.
- Phase 2 (recherche dédiée) : AS embarqué (`oidc-provider`, CIMD expérimental, URL CIMD de claude.ai non documentée), comportement de claude.ai sur `resource` et RFC 9207, tunnel Funnel avec IPv4. Le spike MCP Apps (ticket ext-apps #671, `_meta.ui.visibility`) conditionne le canal de confirmation de la phase 5.
- Phase 3 : RLS avec pool (`SET LOCAL app.member_id` par transaction avec Kysely), `Temporal` dans TS 6.0.3.
- Phase 5 (recherche dédiée) : canal de confirmation (MCP App `visibility: ["app"]` ou page hors bande), `destructiveHint` et « Always allow ». Les défauts de politique sont à arrêter ici.
- Phase 8 (recherche dédiée) : `ofx-data-extractor` / `csv-parse` contre un parseur maison sur fixtures réelles, disponibilité de `listTools().fileArgs` chez les lecteurs du foyer.
- Phase 9 (recherche dédiée) : couverture des banques du foyer, comptes de plusieurs membres en mode restreint, CGU et quotas réels.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Socle et quality gate | 4/14 | In Progress | - |
| 2. Connecteur Claude et identité du foyer | 0/TBD | Not started | - |
| 3. Comptes cloisonnés et catégories | 0/TBD | Not started | - |
| 4. Saisie conversationnelle et soldes | 0/TBD | Not started | - |
| 5. Politique d'écriture et confirmation hors modèle | 0/TBD | Not started | - |
| 6. Budgets, épargne, récurrences et analyse | 0/TBD | Not started | - |
| 7. Dettes, règlements et vue d'ensemble | 0/TBD | Not started | - |
| 8. Import de relevés et pointage | 0/TBD | Not started | - |
| 9. Agrégation bancaire DSP2 | 0/TBD | Not started | - |
