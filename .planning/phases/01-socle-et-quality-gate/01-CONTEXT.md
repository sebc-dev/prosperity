# Phase 1: Socle et quality gate - Context

**Gathered:** 2026-11-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Dépôt TypeScript vierge (Node 26, pnpm 12, TS 6.0.3) gardé par une commande unique `pnpm quality`, seul juge en CI (un seul check requis `quality`), qui bloque typage laxiste, violations d'architecture, failles de sécurité, tests faibles, contournements et dépendances non approuvées — avant toute ligne de domaine métier. Couvre QUAL-01 à QUAL-09. Aucune fonctionnalité utilisateur, aucun outil MCP, aucun OAuth (phase 2).

Le stack, les versions, la liste des checks, leurs seuils et sévérités, la répartition pré-commit / pré-push / CI / nightly, la liste des chemins protégés et l'arborescence `src/` sont **déjà fixés** dans `.claude/CLAUDE.md` (§ 3, § 10, § 11) et `.planning/research/SUMMARY.md` : ne pas les rediscuter. Ce document ne tranche que ce qu'ils laissaient ouvert.

</domain>

<decisions>
## Implementation Decisions

### Amorçage des protections
- **D-01:** Les chemins protégés sont écrits librement pendant la phase 1. Le **dernier plan** active le verrou complet (deny agent, CODEOWNERS, job d'intégrité, ruleset sur `main`) et le prouve par un test : une tentative d'édition d'un fichier de config de la gate par l'agent est refusée. Avant ce plan, la relecture humaine de la config de la gate est la seule protection : le plan final doit inclure un point de relecture explicite.
- **D-02:** « Approbation humaine » = **label posé par `sebc-dev`, vérifié par la CI**. Le job lit les événements de la PR (API issues events, `labeled`, `actor.login`) et n'accepte `gate-change-approved` / `deps-approved` que si (a) l'auteur est dans une allowlist versionnée (aujourd'hui : `sebc-dev`) et (b) le label a été posé **après le dernier commit** de la PR. Tout nouveau push retire le label (job sur `synchronize`) : l'approbation est à refaire. Raison : dépôt public, un seul collaborateur, GitHub refuse l'auto-approbation, donc la revue CODEOWNERS native ne peut pas servir. CODEOWNERS reste présent (documentation, et filet si un collaborateur arrive). — **Reversibility:** reversible — on peut passer plus tard à un commit d'approbation signé sans toucher au reste.
- **D-03:** L'agent n'a pas le droit de poser ni retirer des labels : règles deny sur `gh pr edit*--add-label*`, `gh pr edit*--remove-label*`, `gh label*`, `gh api*labels*` (et `gh issue edit*label*`).
- **D-04:** Arrêt local de l'agent en trois couches, la CI restant le juge final : (1) règles `deny` Edit/Write sur les chemins protégés dans `.claude/settings.json` (versionné) ; (2) hook `PreToolUse` sur Bash qui refuse les écritures shell courantes vers ces chemins (`sed -i`, `>`/`>>`, `tee`, `mv`, `cp`, `rm`, `git checkout --`/`restore` sur ces chemins) ; (3) pré-commit lefthook qui refuse un commit touchant ces chemins sans variable d'autorisation humaine. `--no-verify` et `git push --force*` sont refusés à l'agent. Le hook n'a pas besoin d'être exhaustif : le job d'intégrité CI rattrape les contournements exotiques.
- **D-05:** Sous `.claude/`, seul le **sous-ensemble qui peut désarmer la gate** est protégé : `.claude/settings*.json` et `.claude/CLAUDE.md` (plus `CLAUDE.md`/`AGENTS.md` racine s'ils existent). Les dossiers installés par GSD (`.claude/agents/`, `.claude/commands/`, `.claude/gsd-core/`, `.claude/hooks/gsd-*`, `.claude/scripts/`) restent libres pour les mises à jour de GSD. Cela **remplace** l'entrée `.claude/**` de la liste des chemins protégés de SUMMARY.md.
- **D-06:** Le hook de garde de l'agent vit dans **`quality/agent-guard/`** (protégé via `quality/**`), référencé depuis `.claude/settings.json` — pas dans `.claude/hooks/`.

### Preuve de la gate
- **D-07:** Preuve **hybride**. (a) Un **auto-test de la gate** (`quality/selftest/`) : chaque cas = un patch qui introduit UNE violation + l'identifiant de règle attendu ; il est appliqué sur une copie jetable du vrai dépôt (`git worktree`), avec la vraie config, et le cas n'est vert que si le check visé échoue **pour la règle attendue**. Couvre au minimum chaque violation du critère 2 (`as`, `any`, complexité, outil MCP → `adapters/db`, cycle, export mort, bloc dupliqué, secret, SQL concaténé, handler sans `Principal`, action CI non épinglée) plus : test faible (mutation + couverture), hausse du compteur d'échappatoires, seuil baissé, table sans RLS (cf. D-10). (b) **4 à 5 vraies PR GitHub** jouées en passage manuel guidé à la fin de la phase, limitées à ce que seul GitHub prouve : le check requis `quality` bloque le merge ; label posé par toi accepté ; label posé par un autre acteur (bot/`github-actions`) refusé ; label retiré au push suivant ; dépendance ajoutée sans `deps-approved` bloquée.
- **D-08:** L'auto-test tourne sur **toute PR qui touche un chemin protégé** (même liste que le job d'intégrité, ce qui couvre les montées de version Renovate via `package.json`/lockfile) **et en nightly**. Pas sur chaque PR de domaine.

### Module canari
- **D-09:** Le canari est un **vrai module `src/shared/money`, minimal** : type `Money` (montant `bigint` en centimes + devise `char(3)`, EUR seul accepté en v1), parse chaîne → `bigint` (jamais `parseFloat`/`Number()`), répartition au plus grand reste (Σ parts = total), formatage serveur (« 84,00 € »). Pas de change, pas de taux, pas de multi-devise en usage. Tests : exemples + propriétés fast-check (Σ parts = total, aller-retour parse/format). Il doit tenir couverture 100 % lignes+branches et Stryker ≥ 80. Le « test faible » du critère 3 est un **cas d'auto-test** (patch qui retire une assertion), pas un état du dépôt. Pas de module jouet (knip le signalerait comme mort, contraire au budget d'échappatoires à 0). — **Reversibility:** costly — `Money` sera importé par tous les modules à partir de la phase 3.
- **D-10:** L'intégration PostgreSQL de la phase 1 porte sur le **socle de base**, sans table métier : première migration Kysely (SQL brut, forward-only) = rôles séparés migrations / app (app sans droit DDL), schéma, extensions nécessaires. Tests sur PG 18 réel via Testcontainers (une base par worker, `CREATE DATABASE … TEMPLATE` par fichier, `sequence.shuffle` + seed loguée) : version 18.x, `uuidv7()` disponible, rôle app privé de DDL. Les **méta-tests** sont posés dès maintenant, notamment « toute table à `owner_member_id` a RLS actif » : ils passent à vide en phase 1 et un cas d'auto-test (création d'une table sans RLS → échec attendu) prouve qu'ils mordent. Pas de table canari jetable (les migrations forward-only la garderaient pour toujours). — **Reversibility:** one-way — migration forward-only appliquée en base ; la corriger exige une nouvelle migration.

### Outils hors npm et exécution
- **D-11:** Les outils hors npm (gitleaks 8.30.1, semgrep 1.186.0, osv-scanner 2.7.1, actionlint 1.7.12, zizmor 1.32.0, hadolint 2.15.1 ; trufflehog en nightly) **et** Node/pnpm sont épinglés dans un **`mise.toml` versionné**, lu par lefthook sur le poste et par `jdx/mise-action` (épinglée par SHA) en CI. `mise.toml` est ajouté aux chemins protégés. Raison principale : dépôt public, gitleaks doit arrêter un secret en pré-commit, dans la même version qu'en CI.
- **D-12:** Un seul point d'entrée `pnpm quality`, avec un **profil `push`** pour le pré-push (budget ≤ 60 s) qui joue les mêmes checks dans les mêmes versions mais saute les checks lourds (Stryker sur diff, intégration PG complète, osv-scanner, hadolint, zizmor, e2e) en les déclarant `skipped: ci-only` dans `reports/gate.json` — jamais en silence. La CI joue le profil complet. **Lecture du critère de succès 1 et de QUAL-01 pour cette phase :** « même verdict pour chaque check joué en local et en CI, mêmes versions, même commande ; la CI est le seul juge ». Le vérificateur de phase doit le lire ainsi, pas comme « pré-push = CI complète ».
- **D-13:** La CI tourne sur les **runners hébergés par GitHub** (`ubuntu-latest` épinglé à une version d'image explicite), jamais sur un runner auto-hébergé : le dépôt est public et du code de fork s'exécuterait sur le homelab. Les workflows utilisent `pull_request`, jamais `pull_request_target`.

### Claude's Discretion
- Découpage exact des plans de la phase 1 (le découpage « squelette → types/lint → archi → tests/mutation → sécurité/deps → CI + verrou » des pages de décision est indicatif), à condition que le verrou (D-01) soit le dernier plan.
- Format des cas d'auto-test (`.patch` + `expected.json` ou équivalent) et du rapport `reports/gate.json`, dans le respect du schéma `{check, tool, version, severity, passed, issues[]}` déjà fixé.
- Détails du parseur shell du hook de garde (D-04).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Périmètre et exigences
- `.planning/ROADMAP.md` § « Phase 1: Socle et quality gate » — objectif et 5 critères de succès (critère 1 à lire selon D-12)
- `.planning/REQUIREMENTS.md` — QUAL-01 à QUAL-09
- `.planning/STATE.md` § Blockers/Concerns — compatibilité Stryker 10.1 / Vitest 5.1 à vérifier, bug Stryker #6004 (ne pas committer l'incrémental)

### Stack et gate (décisions déjà verrouillées)
- `.claude/CLAUDE.md` § 3 (stack et versions), § 10 (Quality Gate : tableau des checks, chemins protégés, répartition PC/PP/CI/N, stratégie de test), § 11 (compatibilités de versions)
- `.planning/research/SUMMARY.md` — synthèse de la gate (lignes A à D), liste des chemins protégés (amendée par D-05 et D-11), répartition des étapes
- `.planning/research/STACK.md` — détail des versions et des outils
- `.planning/research/ARCHITECTURE.md` § « Recommended Project Structure » et « Graphe de dépendances » — arborescence `src/` et règles de couches que dependency-cruiser doit encoder (exemples hérités de Python à traduire en TS)
- `.planning/research/PITFALLS.md` — pièges liés au code écrit par agents (tests faibles, édition des tests, affaiblissement de la gate)

### Référence historique
- `origin/main:docs/ci.md`, `origin/main:runbooks/ci.md`, `origin/main:.claude/quality.json` — ancienne gate Python, à titre de comparaison uniquement (le code de `main` n'est pas repris)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Aucun code applicatif : la branche `sebc-dev/jiaolong` ne contient que `.planning/` et `.claude/CLAUDE.md`.

### Established Patterns
- `.claude/` contient l'installation locale de GSD (agents, commandes, `gsd-core/`, une trentaine de hooks `gsd-*.js`, `scripts/`), non suivie par git à ce jour. Pas de `.claude/settings.json` existant : il sera créé par la phase (règles deny + déclaration du hook de garde). Veiller à ne pas casser les hooks GSD déjà déclarés ailleurs.

### Integration Points
- Dépôt GitHub `sebc-dev/prosperity`, **public**, un seul collaborateur (`sebc-dev`), branche par défaut `main`. Les rulesets / protections de branche sont disponibles gratuitement (dépôt public).
- La protection de branche cible `main` ; le travail se fait sur `sebc-dev/jiaolong`, à merger dans `main` par PR.

</code_context>

<specifics>
## Specific Ideas

- Les pages de décision de cette discussion (artefacts « Verrou de la quality gate » et « Preuve et outillage de la gate ») contiennent les diagrammes de référence : couches de défense locales, parcours du label lié au dernier commit, déroulé d'un cas d'auto-test, répartition des checks pré-commit / pré-push / CI.
- Hors code, à lancer pendant la phase 1 (rappel de STATE.md) : enregistrement de l'application Enable Banking (mode restricted production, délais) et collecte de relevés OFX/CSV anonymisés des banques du foyer pour les spikes de la phase 8.

</specifics>

<deferred>
## Deferred Ideas

- Commit d'approbation signé (clé inaccessible à l'agent) en remplacement du label, si un jour l'agent dispose d'un jeton capable de contourner D-02/D-03.
- Runner CI auto-hébergé : écarté tant que le dépôt est public.

</deferred>

---

*Phase: 01-socle-et-quality-gate*
*Context gathered: 2026-11-21*
