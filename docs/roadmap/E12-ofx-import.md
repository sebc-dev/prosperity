# E12 — OFX import (F04 partie 1)

> **Durée estimée** : 5-7 jours
> **Statut** : not started
> **Dépend de** : E05, E07
> **Bloque** : — (Enable Banking en V1 est un epic séparé)
> **ADRs activés** : 0009 (Provider/Reader split, même pour OFX où Reader trivial)

---

## Objectif

Implémenter F04 partie 1 : import OFX manuel (1.x SGML + 2.x XML), parser via `ofxparse` + wrapper défensif, encoding detection déterministe, dedup hash composite, preview hybride conditionnel, mapping persistant des comptes externes vers comptes internes.

Livrable agrégé : un user upload un OFX, l'app détecte l'encoding, lui demande de lier le compte OFX à un compte interne (si pas déjà mappé), affiche une preview si des critères de risque sont rencontrés, et importe les transactions en `draft` (dedupliquées).

> **Note de réconciliation — stories #176–#180 (2026-06-07).** Quatre deltas appliqués au découpage ci-dessous vs la version initiale :
> 1. **Graphe directionnel (contrat import-linter #1)** : `banking ⊥ transactions` (modules pairs, même layer) ⇒ le `commit` qui crée des `Transaction` **ne peut pas vivre dans `banking`**. Les routes d'import + l'orchestration `commit` vivent au **composition root** (`backend/transports/imports_http.py`, hors `backend.modules`), comme `main.py`. `banking` n'expose que parse/analyze/link/log.
> 2. **État d'import = `draft`, pas `planned`/`confirmed`** : `transition_to_planned` impose le zero-sum ; une ligne non catégorisée (jambe `funding` seule) n'est pas équilibrable. L'utilisateur catégorise ensuite (manuel).
> 3. **Numéros de migration** : head Alembic = `0016` ⇒ `0017_bank_account_external_refs`, `0018_imported_transactions` (les `0014`/`0015` ci-dessous étaient périmés).
> 4. **`OFXProvider` n'implémente PAS le Protocol `BankingProvider`** (ADR 0009, pull-only/polling) : c'est un parser fichier statique sibling, partageant `BankTransaction` + la hiérarchie `BankingProviderError`. Le commit `/preview`↔`/commit` est **stateless (re-upload)**, pas de `parsed_ofx_token`.

---

## Stories

### S12.1 — `bank_account_external_refs` table

| Phase | Description | Diff |
|---|---|---|
| **P12.1.1** | Modèle `BankAccountExternalRef` : `id`, `external_ref` text (compte du fichier OFX, ex. numéro masqué), `internal_account_id` FK, `provider` text ('ofx', 'enable_banking' future), `created_at`. Unique `(external_ref, provider)`. Migration `0017_bank_account_external_refs.py`. **+ Restructuration import-linter** : scinder un contrat `2-banking` dédié (miroir `2-transactions`) et retirer `banking` des sources du contrat #2 — obligatoire dès le 1ᵉʳ internal `banking`. Test niveau 1 + test architecture | ~160 |
| **P12.1.2** | Service `banking/service/external_refs.py` : `find_internal_account(external_ref, provider)`, `link(external_ref, internal_id, provider)`. Tests | ~100 |

---

### S12.2 — `OFXProvider` (wrapper défensif autour de `ofxparse`)

| Phase | Description | Diff |
|---|---|---|
| **P12.2.1** | Add dep `ofxparse`. `modules/banking/providers/ofx.py` : `OFXProvider`, **parser fichier statique sibling** — **PAS** une implémentation du Protocol `BankingProvider` (ADR 0009 = pull-only/polling, hors scope OFX). `parse(file_bytes) → ParsedOFX(accounts, transactions, encoding_confidence)`, exécuté via `asyncio.to_thread` (ofxparse synchrone). Pas de `list_accounts`/`fetch_transactions`/`consent_status` | ~150 |
| **P12.2.2** | `_detect_encoding(blob)` : BOM-first (UTF-8 sig, UTF-16), puis tentative UTF-8 strict, sinon fallback windows-1252 avec `encoding_confidence='low'`. Tests avec 4 fixtures (BOM UTF-8, no BOM UTF-8, windows-1252, UTF-16). Cf. CONTEXT.md "Import OFX" | ~180 |
| **P12.2.3** | Wrapper exceptions : `ofxparse.OfxParserException` → `IncompatibleAccountError`, `OSError` → `ProviderUnavailableError`, encodage non détecté → `EncodingDetectionError`. Cohérent avec hiérarchie `BankingProviderError` E13 / ADR 0009. Tests | ~120 |
| **P12.2.4** | Mapping fields → `BankTransaction` Pydantic (modèle commun à OFX et Enable Banking) : `external_ref`, `date`, `amount_cents`, `currency`, `payee`, `description`, `fitid` (gardé pour debug mais non utilisé pour dedup). Tests avec OFX 1.x SGML et OFX 2.x XML | ~150 |

---

### S12.3 — Service analyze (preview + dedup), sans écriture

| Phase | Description | Diff |
|---|---|---|
| **P12.3.1** | Table `imported_transactions` : `id`, `account_id`, `import_hash` (sha256 de `(account_id, date, amount, libellé_normalisé)`), `imported_at`, `source` ('ofx'). Unique `import_hash`. Migration `0018_imported_transactions.py`. Test niveau 1 schema | ~90 |
| **P12.3.2** | Normaliseur libellé (`shared/`, strip+lowercase+retrait préfixes bancaires — **identique au `MatchScorer`**) + `import_hash` composite (fonction pure déterministe). Tests unitaires + Hypothesis | ~90 |
| **P12.3.3** | `banking/service/import_ofx.py` : `analyze_import(parsed_ofx, internal_account_id, session) → ImportPreview` : count tx, dedup count (lookup hash contre `imported_transactions`), encoding_confidence, fenêtre temporelle, montant max, les **5 critères F04** (cf. `docs/Sans titre.md` §F04) → `auto_validatable`, `account_not_linked`. **Pas d'écriture DB** (le commit est en S12.4) | ~220 |

---

### S12.4 — Routes import (composition root) + commit en `draft`

> Routes + orchestration au **composition root** (`backend/transports/imports_http.py`, hors `backend.modules`) : `banking ⊥ transactions` interdit le commit dans `banking`. Entrée stateless (re-upload).

| Phase | Description | Diff |
|---|---|---|
| **P12.4.1** | Nouveau `backend/transports/imports_http.py` (hors graphe modules) + `POST /imports/ofx/preview` (multipart) : `banking.public.parse_ofx` → `analyze_import` → `ImportPreview` JSON ; compte non lié → **422 typé `account_not_linked`**. Router monté dans `main.py`. Tests httpx | ~150 |
| **P12.4.2** | `POST /imports/ofx/link-account` : `banking.public.link` (crée `BankAccountExternalRef`), refuse un compte interne inaccessible. Tests | ~100 |
| **P12.4.3** | `POST /imports/ofx/commit` (re-upload + `internal_account_id`) : pour chaque tx **non dupliquée**, `transactions.public.create_draft` + `add_split` (jambe `funding`) ⇒ **reste `draft`** (zero-sum interdit `planned` sans catégorie ; « Sans catégorie » banni). Log `imported_transactions`. Idempotent (UNIQUE `import_hash`). Frontière `get_db` (ADR 0015), import atomique. Tests intégration | ~250 |

---

### S12.5 — Tests fixtures OFX (6 cas critiques)

| Phase | Description | Diff |
|---|---|---|
| **P12.5.1** | Créer les 6 fixtures listées dans Stratégie de tests §8 : `livret_a_2026_q1.ofx` (OFX 1.x SGML windows-1252), `pel_2025_2026.ofx` (1.x SGML UTF-8 BOM), `boursorama_export_2026.ofx` (2.x XML), `fitid_unstable_societe_generale.ofx`, `account_not_yet_linked.ofx`, `libelles_accentues_windows_1252.ofx` | ~80 (fixtures + harness) |
| **P12.5.2** | Tests d'intégration cassants tous les cas : preview retourne les bons critères, commit dedup correctement, libellés accentués correctement décodés, compte non lié → 422 typé "account_not_linked" demandant le mapping | ~200 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S12.1 (2 phases) | Fondations banking + external refs (#176) | 270 | 270 |
| S12.2 (4 phases) | OFXProvider parser statique (#177) | 600 | 870 |
| S12.3 (3 phases) | Service analyze + dedup (#178) | 400 | 1270 |
| S12.4 (3 phases) | Routes (composition root) + commit (#179) | 500 | 1770 |
| S12.5 (2 phases) | Fixtures + tests (#180) | 280 | 2050 |
| **Total** | **5 stories / 14 phases** | **~2050 lignes** | |

---

## Critères d'acceptation

- [ ] OFX 1.x SGML et OFX 2.x XML tous deux supportés
- [ ] Encoding détecté avec confiance (BOM ou UTF-8 strict) → `encoding_confidence='high'`, sinon `'low'` et preview obligatoire
- [ ] Dedup par hash composite (`account_id`, `date`, `amount`, `libellé_normalisé`) ; FITID jamais utilisé pour dedup
- [ ] Compte OFX non lié → 422 typé `account_not_linked`, route `/link-account` permet d'établir le mapping
- [ ] Pas de création automatique de compte interne — toujours acte utilisateur explicite
- [ ] Transactions importées en état `draft` (jambe `funding` seule, non équilibrée ⇒ `planned` impossible ; catégorisation manuelle pour passer `planned`/`confirmed`)
- [ ] Coverage `OFXProvider` ≥ 80%, service import ≥ 75%

---

## Notes pour l'implémenteur

- `ofxparse` est synchrone. Le wrapper exécute le parsing dans un thread executor (`asyncio.to_thread`) pour ne pas bloquer FastAPI event loop sur les gros fichiers (~50 lignes mais en cas de plusieurs MB d'OFX, ça bloquerait).
- Entrée `/preview` ↔ `/commit` : **re-upload stateless** (le client re-poste le fichier au commit). Pas de `parsed_ofx_token`, pas de fichier temp, pas de cleanup, pas de PII au repos. Le token est une optimisation V1.5 si le double-upload devient gênant.
- Le state `draft` à l'import est conservateur — l'utilisateur catégorise chaque tx (ajout d'une jambe `classification`) pour la faire passer `planned`/`confirmed`. Si trop pénible à l'usage, V1.5 = auto-confirm avec catégorie "À catégoriser" exempte de l'invariant `UncategorizedExpenseError` (mais ça contredit la décision E06).
- Le `libellé_normalisé` du hash composite : `strip + lowercase + retire les préfixes bancaires standard` (cf. CONTEXT.md MatchScorer). Cohérence avec la reconciliation V1.
