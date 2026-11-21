# Prosperity — Connecteur Claude

## What This Is

Prosperity est l'application de finances partagées d'un foyer, repensée en **connecteur pour Claude** : un backend auto-hébergé, exposé comme serveur MCP distant, qui porte toute la logique métier et tous les calculs (transactions, budgets, dettes entre membres, import bancaire, pointage, épargne). Claude est la seule interface. Il récupère les données dont il a besoin, répond aux questions d'analyse et construit des **artefacts** (tableaux de bord, formulaires, écrans de tri) qui se remplissent avec les données du connecteur et permettent aussi la saisie. Les utilisateurs sont les N membres d'un foyer, chacun connecté à Claude avec sa propre identité.

## Core Value

Chaque membre du foyer peut, en une phrase à Claude, **saisir** une dépense ou **voir** l'état exact et à jour des finances du foyer (soldes, budgets, dettes). Les chiffres viennent d'un backend qui calcule juste et ne montre à chacun que ce qu'il a le droit de voir.

## Requirements

### Validated

(Aucune pour l'instant : à valider en livrant)

### Active

- [ ] Serveur MCP distant (HTTPS public + OAuth), ajoutable comme connecteur claude.ai par chaque membre, avec son identité propre
- [ ] Foyer de N membres : rôles admin/member, invitations, bootstrap du premier admin
- [ ] Cloisonnement strict : un compte personnel n'est visible que de son propriétaire (même l'admin n'y a pas accès) ; Claude ne voit que ce que le membre connecté a le droit de voir
- [ ] Comptes personnels et communs, avec quotes-parts par membre
- [ ] Catégories hiérarchiques (archivage plutôt que suppression)
- [ ] Transactions à splits en double-entrée, aggregate immuable une fois `confirmed` (correction = `void` + nouvelle transaction)
- [ ] Saisie conversationnelle : « j'ai payé 84 € de courses, partagé 50/50 » → transaction créée
- [ ] Politique d'écriture paramétrable **par membre et par type d'action** : écriture directe, proposer-puis-confirmer (action en attente), ou selon le risque
- [ ] Budgets par catégorie et par période, scope perso ou commun, alertes de seuil (80 %/100 %)
- [ ] Dettes calculées côté serveur (projection) : excédent budgétaire sur compte commun → dette (F10), demandes de partage sur compte perso, `debt_generation_override`, ajustement de `share_ratio`
- [ ] Règlements (settlements) multi-dettes : virement interne, virement externe, compensation virtuelle
- [ ] Import bancaire par fichier (OFX/CSV) **et** par agrégation DSP2
- [ ] Pointage : suggestions de rapprochement transaction locale ↔ transaction bancaire, confirmées par l'utilisateur (pas d'auto-confirm)
- [ ] Objectifs d'épargne : allocations sur comptes, projections (90 jours glissants)
- [ ] Outils MCP de lecture qui renvoient des **agrégats prêts à afficher** (l'artefact n'a qu'à rendre)
- [ ] Artefacts claude.ai qui lisent (`watchTool`) et écrivent (`callTool`) via la capacité `mcp` : tableau de bord, formulaire de saisie, écran de tri de l'import
- [ ] Questions d'analyse (« pourquoi on a dépassé en restaurants ? ») servies par des outils d'analyse du backend

### Out of Scope

- Clients web (Vite), Android (Capacitor) et la sync PowerSync de l'ancien Prosperity : abandonnés, Claude et les artefacts sont la seule interface
- Reprise du code de `main` : le code est réécrit. Seul le savoir métier (CONTEXT.md, ADR) sert de référence
- Multi-devise en usage : le modèle reste multi-devise, l'usage est verrouillé à EUR en v1 (cf. ancien ADR 0008)
- Auto-confirmation du pointage : l'utilisateur reste dans la boucle, quel que soit le score
- Multi-foyers par instance : un déploiement = un foyer
- Hébergement cloud managé : l'instance est auto-hébergée (homelab)

## Context

- **Projet de reprise** : la branche `main` du dépôt contient un Prosperity complet (backend Python 3.13 / FastAPI / Postgres 17, 19 ADR, roadmap E01–E19, client Vite/Capacitor, PowerSync). On repart d'une branche vide (`sebc-dev/jiaolong`). Le modèle de domaine de `origin/main:CONTEXT.md` et les ADR `origin/main:docs/adr/` sont la référence métier : vocabulaire (Foyer, Compte commun, Quote-part, Split, Pointage, Settlement, Excédent budgétaire, `debt_generation_override`…), invariants (zero-sum des splits, immutabilité à `confirmed`, dettes en projection serveur, solde de dette = montant − Σ lignes de règlement) et règles F10 (budget couvrant le plus spécifique, restant R borné, ordre total `(date, id)`, reclassement).
- **L'ancien ADR 0004 « MCP comme module »** prévoyait déjà des PendingActions (`propose_*` → confirmation → écriture via les services métier), un audit immuable et un rate limiting par jeton. Le connecteur généralise cette idée : le MCP devient l'interface principale.
- **Capacités des artefacts (vérifiées le 2026-11-21, contrat runtime 0.2.98)** : une page publiée peut déclarer la capacité `mcp` et appeler les connecteurs claude.ai **du lecteur**, avec ses identifiants. `watchTool` sert l'affichage (cache, rafraîchissement), `callTool` les actions déclenchées par un geste. Chaque lecteur consent une fois. La saisie via artefact est donc possible. Alternative à évaluer : **MCP Apps**, où le serveur livre ses propres interfaces, rendues dans la conversation.
- **Usages cibles** : saisie conversationnelle, tableau de bord à la demande, questions d'analyse, import du relevé puis tri/pointage/catégorisation dans un artefact.
- **Hébergement** : serveur perso / homelab, exposé publiquement via un tunnel (l'ancien plan visait Quadlet + Caddy + Cloudflare Tunnel).

## Constraints

- **Interface** : Claude (claude.ai + artefacts) est l'unique client. Toute fonctionnalité passe par des outils MCP — pas d'UI web propre au backend, hormis les écrans d'auth/OAuth nécessaires
- **Connecteur distant** : un connecteur claude.ai exige une URL HTTPS publique et un flux OAuth conforme à la spec d'autorisation MCP. C'est un prérequis à tout le reste
- **Sécurité / vie privée** : identité par membre de bout en bout. Les outils filtrent selon l'utilisateur authentifié, jamais selon ce que Claude demande. Données financières réelles d'un foyer
- **Exactitude** : les calculs (dettes, budgets, soldes) sont faits côté serveur, de façon déterministe et idempotente. Claude ne calcule rien qui fasse foi
- **Hébergement** : auto-hébergé sur homelab, ressources modestes, déploiement simple et sauvegardable
- **Bancaire** : l'agrégation DSP2 passe par un agrégateur tiers (à choisir : Enable Banking, GoCardless…), avec ses contraintes de consentement (renouvellement à 90/180 jours)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Repartir de zéro sur une branche vide, savoir métier de `main` comme référence | Le domaine est mûr, l'architecture client/sync ne correspond plus à la cible | — Pending |
| Claude + artefacts comme seule interface (abandon web/Android/PowerSync) | Le connecteur MCP remplace l'UI. Moins de surface à maintenir | — Pending |
| Backend = serveur MCP distant qui fait tout le traitement | Claude et les artefacts ne font que demander et rendre ; les chiffres font foi côté serveur | — Pending |
| Saisie via artefacts par la capacité `mcp` (callTool) | Vérifié possible sur le contrat runtime actuel | — Pending |
| Politique d'écriture paramétrable par membre et par type d'action | Concilier fluidité (écriture directe) et sécurité (confirmation pour l'irréversible) | — Pending |
| Cloisonnement strict des comptes personnels, identité par membre | Exigence héritée, non négociable avec des données de foyer réelles | — Pending |
| Auto-hébergement homelab | Contrôle des données financières | — Pending |
| Stack backend | À déterminer par la recherche (l'ancien choix Python/FastAPI/Postgres reste un candidat) | — Pending |
| Artefacts claude.ai vs MCP Apps pour les interfaces | À déterminer par la recherche | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-21 after initialization*
