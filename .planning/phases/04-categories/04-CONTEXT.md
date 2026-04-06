# Phase 4: Categories - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Un système de catégories hiérarchiques existe — catégories Plaid de base seedées + catégories custom créées par les utilisateurs — que les transactions et les enveloppes utiliseront pour la classification. Phase 5 (Transactions) et Phase 6 (Envelopes) dépendent de Phase 4. Les règles de catégorisation automatique (CATG-05/06) sont hors scope.

</domain>

<decisions>
## Implementation Decisions

### Propriété des catégories
- **D-01:** Les catégories sont **globales au foyer** — ni les catégories Plaid ni les catégories custom ne portent de `user_id`. Une catégorie custom créée par un utilisateur est visible par tous les membres du foyer. L'entité `Category.java` existante est déjà correcte (pas de champ user à ajouter).

### Seeding des catégories Plaid de base
- **D-02:** Les catégories Plaid sont seedées via une **migration Flyway** (V010 ou suivant). Set curated de ~20-30 catégories pertinentes pour un foyer français : Alimentation, Transport, Logement, Santé, Loisirs, Vêtements, Abonnements, Épargne, Revenus, Divers. Structure hiérarchique 2 niveaux (parent/enfant). Le champ `plaid_category_id` est renseigné pour les catégories mappées à la taxonomie Plaid officielle.
- **D-03:** Les catégories Plaid sont **non éditables par l'utilisateur** (read-only dans l'UI). Un flag ou convention de nommage distingue Plaid vs custom — préférence pour un booléen `is_system BOOLEAN NOT NULL DEFAULT FALSE` ajouté via migration (absent de V004).

### Catégories custom
- **D-04:** L'utilisateur peut créer des catégories custom **racine** ou **enfant** d'une catégorie existante (Plaid ou custom). Profondeur max : 2 niveaux (parent/enfant) — pas de récursion arbitraire. Cohérent avec CATG-04 et la structure de Transaction.
- **D-05:** L'utilisateur peut **renommer et supprimer** ses catégories custom. Suppression bloquée si la catégorie est utilisée par des transactions (contrainte d'intégrité → 409 Conflict).

### Portée de CATG-02 (changement de catégorie sur transaction)
- **D-06:** `PATCH /api/transactions/{id}/category` implémenté en **Phase 4**. Corps : `{"categoryId": "uuid"}`. Pas d'UI transaction en Phase 4 — la liste des transactions, la création, les filtres arrivent en Phase 5. CATG-02 est validé dès que l'endpoint fonctionne (test d'intégration suffit).

### Interface de gestion des catégories (Frontend)
- **D-07:** Page dédiée `/categories` accessible depuis la sidebar. Pattern identique à la page `/accounts` (Phase 3) : `p-table` PrimeNG avec colonnes Nom, Catégorie parente, Type (Plaid/Custom), Actions. Tri natif.
- **D-08:** Création et édition via `p-dialog` PrimeNG — formulaire avec champ nom + sélecteur de catégorie parente (optionnel). Cohérent avec D-11 de Phase 3.
- **D-09:** Les catégories Plaid sont affichées en lecture seule dans la table (pas de bouton Éditer/Supprimer). Badge ou icône distinctif pour les catégories système.
- **D-10:** Le sélecteur de catégorie (utilisé dans les dialogs et futur écran transaction) est un **composant partagé** réutilisable — `p-select` ou `p-treeSelect` PrimeNG avec affichage hiérarchique (parent > enfant).

### Claude's Discretion
- Nommage exact des endpoints REST
- Structure exacte des DTOs (records Java)
- Choix entre `p-select` et `p-treeSelect` pour le sélecteur hiérarchique (dépend de la lisibilité avec 2 niveaux)
- Styles Tailwind/PrimeNG pour les badges Plaid/Custom
- Format exact des identifiants `plaid_category_id` dans la migration

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & patterns
- `docs/adr/0002-architecture-layered.md` — Layered by feature, package `category/` location
- `docs/agent_docs/architecture.md` — Structure backend, composants, flux de données
- `.planning/phases/03-accounts-access-control/03-CONTEXT.md` — Patterns Controller/Service/DTO + UI (p-table, p-dialog) établis en Phase 3

### Database schema
- `backend/src/main/resources/db/migration/V004__create_categories.sql` — Schema actuel `categories` (sans colonne `is_system`)
- `backend/src/main/resources/db/migration/V005__create_transactions.sql` — Relation `category_id` dans `transactions`
- `docs/agent_docs/database.md` — Schema complet PostgreSQL, relations

### Entités existantes (Phase 1)
- `backend/src/main/java/com/prosperity/category/Category.java` — Entité existante à compléter
- `backend/src/main/java/com/prosperity/category/CategoryRepository.java` — Repository vide à enrichir
- `backend/src/main/java/com/prosperity/transaction/Transaction.java` — Champ `category` (ManyToOne optionnel) déjà présent

### Frontend référence
- `frontend/src/app/accounts/` — Module accounts complet à utiliser comme modèle de structure Angular

### Requirements
- `.planning/REQUIREMENTS.md` §CATG-01 à CATG-04 — Critères d'acceptation à valider

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Category.java` : entité JPA complète (id UUID, name, parent self-ref ManyToOne, plaidCategoryId, createdAt) — à compléter avec `isSystem`
- `CategoryRepository.java` : étend JpaRepository — à enrichir avec queries (findRoots, findByParent, findCustom)
- `Transaction.java` : champ `category` (ManyToOne LAZY, JoinColumn `category_id`) — endpoint PATCH à brancher dessus
- `V004__create_categories.sql` : table `categories` déjà créée en DB — migration complémentaire requise pour `is_system`

### Established Patterns
- Controller/Service/Repository par feature — package `com.prosperity.category`
- DTOs sous forme de records Java (cf. AccountResponse, AccountRequest en Phase 3)
- Exceptions custom (`AccountNotFoundException` → `CategoryNotFoundException`)
- Tests d'intégration avec Testcontainers PostgreSQL (cf. AccountControllerTest)
- Frontend : service Angular + composant page + dialog, OnPush + signals (cf. accounts module)

### Integration Points
- `Transaction.java` → `category_id` FK — endpoint PATCH /api/transactions/{id}/category mis à jour en Phase 4
- Sidebar Angular (`layout/`) → lien `/categories` à ajouter (cf. lien `/accounts` ajouté en Phase 3)
- `app.routes.ts` → route `/categories` à enregistrer
- Phase 5 (Transactions) consommera le sélecteur de catégorie créé en Phase 4
- Phase 6 (Envelopes) consommera également les catégories pour l'affectation d'enveloppes

</code_context>

<specifics>
## Specific Ideas

- Taxonomie curated pour la France : Alimentation & Restauration, Transport, Logement (Loyer, Charges), Santé, Loisirs & Culture, Vêtements & Beauté, Abonnements & Services, Épargne & Investissements, Revenus, Divers — avec sous-catégories pour les plus volumineuses (ex : Alimentation > Courses, Alimentation > Restaurant)
- Le sélecteur de catégorie doit fonctionner comme référence réutilisable — Phase 5 et 6 l'importeront directement

</specifics>

<deferred>
## Deferred Ideas

- CATG-05 : Règles de catégorisation automatique (libellé contient X → catégorie Y) — hors scope, à prévoir dans un backlog futur
- CATG-06 : Suggestions de catégorie basées sur l'historique — hors scope, nécessite ML ou règles statistiques
- Import/export des catégories custom (CSV ou JSON) — idée raisonnable mais hors Phase 4
- Catégories couleur-codées ou avec icônes — UX enhancement, reporté au dashboard Phase 10

### Reviewed Todos
Aucun todo pending ne correspondait à cette phase.

</deferred>

---

*Phase: 04-categories*
*Context gathered: 2026-04-05*
