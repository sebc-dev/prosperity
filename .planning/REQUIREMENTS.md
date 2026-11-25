# Requirements: Prosperity — Connecteur Claude

**Defined:** 2026-11-21
**Core Value:** Chaque membre du foyer peut, en une phrase à Claude, saisir une dépense ou voir l'état exact et à jour des finances du foyer (soldes, budgets, dettes). Les chiffres viennent d'un backend qui calcule juste et ne montre à chacun que ce qu'il a le droit de voir.

**Référence métier :** `origin/main:CONTEXT.md` et `origin/main:docs/adr/` (vocabulaire, invariants, règle F10). **Recherche :** `.planning/research/SUMMARY.md`.

## v1 Requirements

### Quality gate & socle (QUAL)

- [x] **QUAL-01**: Une commande unique `pnpm quality` joue la gate complète, identique en pré-push et en CI ; la CI est l'unique juge (un seul check requis)
- [x] **QUAL-02**: La gate bloque sur typage strict (`tsc` strict, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`), lint type-aware sans avertissement, assertions de type interdites (`as` hors `as const`, `any`, `!`) et complexité plafonnée
- [x] **QUAL-03**: La gate bloque toute violation des frontières d'architecture (dependency-cruiser : domaine pur, accès cross-module par API publique, outils MCP sans accès direct à la base, aucun cycle), le code mort et les dépendances non déclarées (knip), et la duplication nouvelle (jscpd)
- [x] **QUAL-04**: La gate bloque sur les secrets (gitleaks), les règles Semgrep du projet (handler sans `Principal`, SQL concaténé, aléa non cryptographique pour un jeton), les CVE high/critical des dépendances, et les workflows CI non épinglés
- [x] **QUAL-05**: Le noyau financier est couvert par des tests de propriétés (fast-check) sur ses invariants, et le mutation testing (Stryker) bloque sous le seuil sur les fichiers de domaine modifiés ; couverture 100 % sur le domaine pur, plancher global à cliquet
- [x] **QUAL-06**: Un compteur d'échappatoires (`@ts-ignore`, `eslint-disable`, `.skip`, `as any`, `vi.mock(`…) à cliquet bloque toute hausse ; un job d'intégrité bloque toute baisse de seuil ou tout retrait d'assertion sans approbation humaine explicite
- [x] **QUAL-07**: Les chemins de configuration de la gate, de CI et de déploiement sont protégés contre la modification par un agent (CODEOWNERS, permissions agent, job d'intégrité)
- [x] **QUAL-08**: Les tests d'intégration tournent contre un vrai PostgreSQL 18 (Testcontainers), sans mock de repository, en ordre aléatoire
- [x] **QUAL-09**: Toute nouvelle dépendance exige une approbation humaine et un âge minimal de publication (politique supply-chain pnpm)

### Connecteur & authentification (CONN)

- [ ] **CONN-01**: Un membre peut ajouter Prosperity comme connecteur personnalisé claude.ai via une URL HTTPS publique stable et s'y authentifier par OAuth (PKCE S256, RFC 8707, rotation des refresh tokens)
- [ ] **CONN-02**: Le serveur répond aux exigences claude.ai : `401` avec `resource_metadata`, métadonnées PRM/AS conformes, hostname IPv4 public, aucune redirection inter-hôtes, endpoints d'auth sous 10 s
- [ ] **CONN-03**: L'enregistrement de client est restreint (CIMD limité à claude.ai/claude.com, redirect URI exactes, DCR désactivé, client statique en filet)
- [ ] **CONN-04**: Chaque appel d'outil est rattaché au membre authentifié via le jeton (audience vérifiée) ; aucun outil n'accepte d'identifiant de membre en argument
- [ ] **CONN-05**: Le serveur fonctionne en Streamable HTTP sans état de session (compatible avec les specs d'autorisation 2025 que claude.ai parle)
- [ ] **CONN-06**: Un membre peut se connecter avec une passkey sur l'écran d'autorisation (pas de mot de passe maison si évitable)
- [ ] **CONN-07**: Un admin peut révoquer l'accès d'un membre ; ses jetons cessent immédiatement d'être acceptés
- [ ] **CONN-08**: Un outil `whoami` / `get_household_context` renvoie l'identité du membre, ses comptes accessibles, la devise, ses préférences et sa politique d'écriture

### Foyer & accès (FOY)

- [ ] **FOY-01**: Le premier admin est créé par un bootstrap à secret à usage unique, verrouillé après initialisation (aucune page de setup ouverte au public)
- [ ] **FOY-02**: Un admin peut inviter un membre (jeton haché, valable 7 jours, pré-attribué à un email, révocable, rôle toujours `member`)
- [ ] **FOY-03**: Un invité devient membre en consommant son invitation lors de sa première autorisation OAuth
- [ ] **FOY-04**: Un admin peut promouvoir un membre admin (acte séparé, audité)
- [ ] **FOY-05**: Un compte personnel n'est visible que de son propriétaire, admin compris, garanti par RLS Postgres en plus du filtrage applicatif ; une matrice de tests outil × rôle × classe de compte le prouve
- [ ] **FOY-06**: Une ressource inexistante et une ressource inaccessible produisent la même réponse (`not_found`), sans oracle de divulgation

### Comptes & catégories (CPT)

- [ ] **CPT-01**: Un membre peut créer un compte personnel ou un compte commun (≥ 2 membres) avec quote-part par membre en points de base (défaut 50/50)
- [ ] **CPT-02**: Un membre voit, pour chaque compte accessible, le solde réel, prévisionnel et projeté (fin de mois)
- [ ] **CPT-03**: Un membre peut gérer des catégories hiérarchiques (création, déplacement sans cycle, archivage/désarchivage ; jamais de suppression d'une catégorie utilisée)
- [ ] **CPT-04**: Les montants sont stockés en entiers de centimes (`Money`), devise verrouillée EUR au niveau du foyer

### Transactions & saisie (TRX)

- [ ] **TRX-01**: Une transaction est composée de splits dont la somme est nulle (vérifié en domaine et en base), avec états `draft` / `planned` / `confirmed` / `void`
- [ ] **TRX-02**: Une transaction `confirmed` est immuable (montant et splits) ; seuls catégorie, tags, description, `debt_generation_override` et demande de partage restent éditables ; une correction = `void` + nouvelle transaction (outil composite `correct_transaction`)
- [ ] **TRX-03**: Un membre peut saisir une dépense en une phrase (« j'ai payé 84 € de courses, partagé 50/50 ») : l'outil prend l'intention (montant, payeur, catégorie par nom, partage) et le serveur construit les splits
- [ ] **TRX-04**: Si un nom de compte, de catégorie ou de membre est ambigu ou inconnu, l'outil renvoie `needs_clarification` avec les candidats, sans rien écrire
- [ ] **TRX-05**: Un membre peut saisir plusieurs dépenses en une phrase (outil batch, résultat par ligne)
- [ ] **TRX-06**: Un membre peut annuler sa dernière saisie (`void` de la transaction qu'il vient de créer)
- [ ] **TRX-07**: Un membre peut annuler plusieurs transactions en une action (void par lot, soumis à la politique d'écriture)
- [ ] **TRX-08**: Un membre peut envoyer une photo de ticket à Claude, qui propose la transaction (multi-splits) avant écriture
- [ ] **TRX-09**: Un membre peut définir des transactions récurrentes (loyer, abonnements) générées par un job serveur idempotent en `planned`, alimentant le solde projeté
- [ ] **TRX-10**: Un membre peut rechercher et filtrer ses transactions (période, compte, catégorie, montant, texte, tag), avec pagination par curseur et réponses bornées en taille
- [ ] **TRX-11**: Toute écriture exige une clé d'idempotence ; un retry avec la même clé renvoie le résultat initial sans doublon
- [ ] **TRX-12**: Chaque outil d'écriture renvoie l'état résultant (solde, consommation de budget, dette générée, alerte franchie) et un code d'erreur d'un vocabulaire fermé en cas d'échec

### Politique d'écriture & audit (POL)

- [ ] **POL-01**: Chaque membre règle, par type d'action, le mode d'écriture : `direct`, `propose` (action en attente à confirmer) ou `risk_based` (selon montant et type)
- [ ] **POL-02**: Des planchers non configurables s'appliquent (ex. confirmation de pointage jamais `direct` ; identité, droits et politique toujours confirmés hors modèle)
- [ ] **POL-03**: Une action en attente suit le cycle `pending → confirmed | rejected | expired | superseded`, liée au membre, avec empreinte du payload, TTL et revalidation à la confirmation
- [ ] **POL-04**: La confirmation d'une action en attente se fait par un canal que le modèle ne peut pas actionner (MCP App avec outils `visibility: ["app"]`) ; repli documenté sur une page d'approbation hors bande si le rendu MCP Apps n'est pas fiable
- [ ] **POL-05**: Avant confirmation, le membre voit l'effet calculé par le serveur (dette générée, budget consommé)
- [ ] **POL-06**: Chaque action de l'agent est journalisée (qui, quoi, quand, mode, résultat) et le membre peut consulter « ce que Claude a fait en mon nom »
- [ ] **POL-07**: Les écritures sont limitées en débit par grant OAuth

### Budgets (BUD)

- [ ] **BUD-01**: Un membre peut créer un budget par catégorie et période (mensuel par défaut), scope perso ou commun, avec contributeurs ; il agrège les sous-catégories
- [ ] **BUD-02**: Un membre voit la consommation, le restant (borné à ≥ 0) et le statut de chaque budget, calculés serveur
- [ ] **BUD-03**: Les alertes de seuil 80 % / 100 % remontent dans les réponses d'écriture et à l'ouverture du tableau de bord
- [ ] **BUD-04**: Créer, modifier ou archiver un budget re-matérialise les dettes F10 des transactions couvertes, de façon déterministe et idempotente, avec trace d'audit
- [ ] **BUD-05**: Un membre peut simuler l'effet d'un changement de budget sur les dettes avant de l'appliquer (`simulate_budget_change`)

### Dettes & règlements (DET)

- [ ] **DET-01**: Une dépense sur compte commun génère une dette de quote-part sur l'excédent budgétaire (règle F10 : budget couvrant le plus spécifique, ordre total `(date, id)`, montant entier sans budget)
- [ ] **DET-02**: Un membre peut créer une demande de partage depuis un compte personnel (libellé court) ; le débiteur ne voit jamais la transaction ni le compte source
- [ ] **DET-03**: Un membre peut ajuster la `share_ratio` d'une dette et le `debt_generation_override` d'une transaction (`default` / `force_full_debt` / `force_no_debt`)
- [ ] **DET-04**: Un membre voit qui doit combien à qui (solde net et détail par dette, solde = montant − Σ lignes de règlement)
- [ ] **DET-05**: Un membre peut enregistrer un règlement multi-dettes (virement interne, externe ou compensation virtuelle) avec nettage croisé ligne à ligne
- [ ] **DET-06**: Un règlement n'est effectif qu'après accord des deux membres concernés
- [ ] **DET-07**: Le serveur suggère un plan de règlement pour solder, sans perdre la traçabilité par dette
- [ ] **DET-08**: Un membre peut obtenir l'explication d'une dette (chaîne causale structurée, masquage respecté) via `explain_debt`
- [ ] **DET-09**: Les dettes ont une identité déterministe (upsert) ; un job `verify`/`rebuild` prouve que la projection est égale à son recalcul

### Import & pointage (IMP)

- [ ] **IMP-01**: Un membre peut importer un relevé OFX (1.x SGML et 2.x XML) envoyé tel quel au serveur (argument fichier), sans passer par le contexte du modèle
- [ ] **IMP-02**: Un membre peut importer un relevé CSV de banque française (séparateur `;`, décimale `,`, dates `JJ/MM/AAAA`, encodage détecté)
- [ ] **IMP-03**: L'import affiche un aperçu (compteurs, doublons, plage de dates, anomalies) avant commit, lie le fichier à un compte existant et ne crée jamais de compte
- [ ] **IMP-04**: Réimporter un relevé ne crée aucun doublon (dédup par empreinte), et les lignes sont créées en `draft`
- [ ] **IMP-05**: Un membre trie les lignes importées (catégorie, partage) et valide en lot ; les libellés importés sont traités comme du texte non fiable
- [ ] **IMP-06**: Le serveur suggère des catégories à partir d'une mémoire déterministe des choix passés (libellé normalisé → catégorie)
- [ ] **IMP-07**: Le serveur suggère des pointages transaction locale ↔ ligne bancaire (date, libellé, montant strict) avec explication ; le membre confirme, jamais d'auto-confirmation ; le dépointage ne ramène pas en `planned`

### Agrégation bancaire DSP2 (BNK)

- [ ] **BNK-01**: Un membre peut connecter ses comptes bancaires via Enable Banking (consentement SCA lié au membre)
- [ ] **BNK-02**: Un job serveur synchronise les transactions dans les quotas (≈ 4 lectures/jour/banque) ; aucun outil n'appelle l'agrégateur en synchrone
- [ ] **BNK-03**: Les transactions DSP2 passent par la même dédup et le même pointage que l'import fichier (pas de doublon fichier ↔ DSP2)
- [ ] **BNK-04**: Le membre voit la date de dernière synchronisation et l'expiration du consentement dans les réponses, et est prévenu avant expiration (J-14) avec un lien de renouvellement

### Épargne (EPA)

- [ ] **EPA-01**: Un membre peut créer un objectif d'épargne (cible, date, versement mensuel cible) adossé à un ou plusieurs comptes via des allocations (avertissement, pas d'erreur, en cas de sur-allocation)
- [ ] **EPA-02**: Un membre peut rattacher un versement à un objectif
- [ ] **EPA-03**: Un membre voit la projection sur 90 jours glissants (masquée < 30 j, provisoire 30-90 j, état en avance / dans les temps / en retard)
- [ ] **EPA-04**: Un membre peut simuler un objectif (« combien par mois pour y arriver ? », « et si je saute ce mois ? ») via `simulate_savings`

### Interfaces (UI)

- [ ] **UI-01**: Un artefact tableau de bord affiche soldes, budgets, alertes, dettes, épargne et dernières transactions en lisant le connecteur au chargement (`watchTool`), sans donnée incrustée dans la page
- [ ] **UI-02**: Un artefact formulaire de saisie crée une transaction par `callTool` sur geste explicite, avec clé d'idempotence et listes de comptes/catégories réelles
- [ ] **UI-03**: Un écran de triage d'import permet le dépôt du fichier, l'aperçu, la catégorisation, le pointage et la validation en lot
- [ ] **UI-04**: Un écran dettes & règlements affiche soldes nets, détail, plan suggéré et permet d'enregistrer un règlement
- [ ] **UI-05**: Un écran d'actions en attente (MCP App) liste les actions, montre leur effet et permet de confirmer ou refuser par des outils invisibles du modèle
- [ ] **UI-06**: Des écrans budgets et épargne affichent consommation, alertes, objectifs et projections
- [ ] **UI-07**: Chaque écran gère les états dégradés par code d'erreur (connecteur absent, réauth, refus, données périmées avec fraîcheur affichée) section par section
- [ ] **UI-08**: Les gabarits d'écrans sont distribués par le serveur (ressources MCP) pour une UI stable d'une session à l'autre ; un même artefact partagé montre à chaque membre ses propres données
- [ ] **UI-09**: Les contrats d'outils (noms, `outputSchema`) sont versionnés, évoluent de façon additive et sont figés par un snapshot de `tools/list` relu par un humain

### Analyse (ANA)

- [ ] **ANA-01**: Un membre peut analyser ses dépenses par catégorie, période, compte ou membre, avec comparaison à la période précédente (agrégats serveur)
- [ ] **ANA-02**: Un membre peut demander pourquoi un budget a été dépassé ; l'outil renvoie les contributeurs (plus grosses transactions, écart à la moyenne, pics, payeurs) que Claude narre
- [ ] **ANA-03**: Un prompt `point_mensuel` produit la revue mensuelle du foyer (budgets, dettes, épargne, anomalies)
- [ ] **ANA-04**: Le serveur détecte les dépenses atypiques et les abonnements récurrents (calcul déterministe)

### Exploitation (OPS)

- [ ] **OPS-01**: L'instance se déploie sur homelab en conteneur (image unique, processus `app` et `worker`, Postgres 18) exposée par tunnel ; seules les routes MCP, OAuth et `.well-known` sont publiques
- [ ] **OPS-02**: Une sauvegarde chiffrée hors machine est faite automatiquement et sa restauration est testée
- [ ] **OPS-03**: Une sonde externe surveille la joignabilité du connecteur depuis Internet
- [ ] **OPS-04**: Les secrets (clés OAuth, clés Enable Banking) sont hors git et leur rotation est documentée

## v2 Requirements

### Interfaces

- **UI2-01**: Export CSV d'un relevé ou d'un rapport (capacité `downloads`)
- **UI2-02**: Notifications hors Claude (email) pour les alertes et l'expiration de consentement

### Domaine

- **DOM2-01**: Usage multi-devise (lever le verrou EUR)
- **DOM2-02**: Plancher de politique d'écriture imposé par l'admin au niveau du foyer
- **DOM2-03**: Suggestion de budget à partir de l'historique

## Out of Scope

| Feature | Reason |
|---------|--------|
| Clients web, Android, sync PowerSync | Claude et les artefacts sont la seule interface |
| Outil générique `run_sql` / `api_request` | Contourne cloisonnement et audit ; surface d'injection ; refusé par les critères Anthropic |
| Calcul de splits, dettes ou totaux par Claude ou par l'artefact | Les chiffres font foi côté serveur uniquement |
| Auto-confirmation du pointage | Décision produit : l'humain reste dans la boucle |
| Données financières stockées dans l'artefact (`db`/`artifact`) | Hors backend, hors cloisonnement, partagées avec le lien |
| Lien public sur un artefact connecté | Les appels connecteur ne tournent pas pour un lecteur anonyme |
| Admin qui lit les comptes des autres, reset 2FA par l'admin | Casse le cloisonnement ; vecteur de takeover |
| Virement réel / mouvement d'argent | Un règlement enregistre un fait ; l'argent bouge hors Prosperity |
| Stockage de crédentials bancaires | Agrégateur agréé DSP2 uniquement |
| Multi-foyers par instance, inscription publique | Un déploiement = un foyer ; accès sur invitation |
| Méthode enveloppe YNAB, patrimoine/bourse, conseil financier | Autre produit, hors Core Value |
| Édition de montant d'une transaction `confirmed`, hard-delete | Casse la double-entrée et l'idempotence des dettes |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| QUAL-01 | Phase 1 | Complete |
| QUAL-02 | Phase 1 | Complete |
| QUAL-03 | Phase 1 | Complete |
| QUAL-04 | Phase 1 | Complete |
| QUAL-05 | Phase 1 | Complete |
| QUAL-06 | Phase 1 | Complete |
| QUAL-07 | Phase 1 | Complete |
| QUAL-08 | Phase 1 | Complete |
| QUAL-09 | Phase 1 | Complete |
| CONN-01 | Phase 2 | Pending |
| CONN-02 | Phase 2 | Pending |
| CONN-03 | Phase 2 | Pending |
| CONN-04 | Phase 2 | Pending |
| CONN-05 | Phase 2 | Pending |
| CONN-06 | Phase 2 | Pending |
| CONN-07 | Phase 2 | Pending |
| CONN-08 | Phase 2 | Pending |
| FOY-01 | Phase 2 | Pending |
| FOY-02 | Phase 2 | Pending |
| FOY-03 | Phase 2 | Pending |
| FOY-04 | Phase 2 | Pending |
| FOY-05 | Phase 3 | Pending |
| FOY-06 | Phase 3 | Pending |
| CPT-01 | Phase 3 | Pending |
| CPT-02 | Phase 4 | Pending |
| CPT-03 | Phase 3 | Pending |
| CPT-04 | Phase 3 | Pending |
| TRX-01 | Phase 4 | Pending |
| TRX-02 | Phase 4 | Pending |
| TRX-03 | Phase 4 | Pending |
| TRX-04 | Phase 4 | Pending |
| TRX-05 | Phase 4 | Pending |
| TRX-06 | Phase 4 | Pending |
| TRX-07 | Phase 5 | Pending |
| TRX-08 | Phase 5 | Pending |
| TRX-09 | Phase 6 | Pending |
| TRX-10 | Phase 4 | Pending |
| TRX-11 | Phase 3 | Pending |
| TRX-12 | Phase 4 | Pending |
| POL-01 | Phase 5 | Pending |
| POL-02 | Phase 5 | Pending |
| POL-03 | Phase 5 | Pending |
| POL-04 | Phase 5 | Pending |
| POL-05 | Phase 5 | Pending |
| POL-06 | Phase 5 | Pending |
| POL-07 | Phase 5 | Pending |
| BUD-01 | Phase 6 | Pending |
| BUD-02 | Phase 6 | Pending |
| BUD-03 | Phase 6 | Pending |
| BUD-04 | Phase 7 | Pending |
| BUD-05 | Phase 7 | Pending |
| DET-01 | Phase 7 | Pending |
| DET-02 | Phase 7 | Pending |
| DET-03 | Phase 7 | Pending |
| DET-04 | Phase 7 | Pending |
| DET-05 | Phase 7 | Pending |
| DET-06 | Phase 7 | Pending |
| DET-07 | Phase 7 | Pending |
| DET-08 | Phase 7 | Pending |
| DET-09 | Phase 7 | Pending |
| IMP-01 | Phase 8 | Pending |
| IMP-02 | Phase 8 | Pending |
| IMP-03 | Phase 8 | Pending |
| IMP-04 | Phase 8 | Pending |
| IMP-05 | Phase 8 | Pending |
| IMP-06 | Phase 8 | Pending |
| IMP-07 | Phase 8 | Pending |
| BNK-01 | Phase 9 | Pending |
| BNK-02 | Phase 9 | Pending |
| BNK-03 | Phase 9 | Pending |
| BNK-04 | Phase 9 | Pending |
| EPA-01 | Phase 6 | Pending |
| EPA-02 | Phase 6 | Pending |
| EPA-03 | Phase 6 | Pending |
| EPA-04 | Phase 6 | Pending |
| UI-01 | Phase 7 | Pending |
| UI-02 | Phase 4 | Pending |
| UI-03 | Phase 8 | Pending |
| UI-04 | Phase 7 | Pending |
| UI-05 | Phase 5 | Pending |
| UI-06 | Phase 6 | Pending |
| UI-07 | Phase 4 | Pending |
| UI-08 | Phase 4 | Pending |
| UI-09 | Phase 2 | Pending |
| ANA-01 | Phase 6 | Pending |
| ANA-02 | Phase 6 | Pending |
| ANA-03 | Phase 7 | Pending |
| ANA-04 | Phase 6 | Pending |
| OPS-01 | Phase 2 | Pending |
| OPS-02 | Phase 3 | Pending |
| OPS-03 | Phase 2 | Pending |
| OPS-04 | Phase 9 | Pending |

**Coverage:**
- v1 requirements: 92 total
- Mapped to phases: 92
- Unmapped: 0 ✓

---
*Requirements defined: 2026-11-21*
*Last updated: 2026-11-21 after roadmap creation (traceability: 92/92 mapped across 9 phases)*
