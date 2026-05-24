# E12 — OFX import (F04 partie 1)

> **Durée estimée** : 5-7 jours
> **Statut** : not started
> **Dépend de** : E05, E07
> **Bloque** : — (Enable Banking en V1 est un epic séparé)
> **ADRs activés** : 0009 (Provider/Reader split, même pour OFX où Reader trivial)

---

## Objectif

Implémenter F04 partie 1 : import OFX manuel (1.x SGML + 2.x XML), parser via `ofxparse` + wrapper défensif, encoding detection déterministe, dedup hash composite, preview hybride conditionnel, mapping persistant des comptes externes vers comptes internes.

Livrable agrégé : un user upload un OFX, l'app détecte l'encoding, lui demande de lier le compte OFX à un compte interne (si pas déjà mappé), affiche une preview si des critères de risque sont rencontrés, et importe les transactions en `confirmed` (dedupliquées).

---

## Stories

### S12.1 — `bank_account_external_refs` table

| Phase | Description | Diff |
|---|---|---|
| **P12.1.1** | Modèle `BankAccountExternalRef` : `id`, `external_ref` text (compte du fichier OFX, ex. numéro masqué), `internal_account_id` FK, `provider` text ('ofx', 'enable_banking' future), `created_at`. Unique `(external_ref, provider)`. Migration `0014_bank_account_external_refs.py`. Test niveau 1 | ~120 |
| **P12.1.2** | Service `banking/service/external_refs.py` : `find_internal_account(external_ref, provider)`, `link(external_ref, internal_id, provider)`. Tests | ~100 |

---

### S12.2 — `OFXProvider` (wrapper défensif autour de `ofxparse`)

| Phase | Description | Diff |
|---|---|---|
| **P12.2.1** | Add dep `ofxparse`. `modules/banking/providers/ofx.py` : `OFXProvider` qui implémente `BankingProvider` Protocol (cf. ADR 0009) — mais en mode "fichier statique", pas API. Méthodes adaptées : `parse(file_bytes) → ParsedOFX(accounts, transactions, encoding_confidence)`. Pas les méthodes `list_accounts`/`fetch_transactions` async (OFX est synchrone par nature) | ~150 |
| **P12.2.2** | `_detect_encoding(blob)` : BOM-first (UTF-8 sig, UTF-16), puis tentative UTF-8 strict, sinon fallback windows-1252 avec `encoding_confidence='low'`. Tests avec 4 fixtures (BOM UTF-8, no BOM UTF-8, windows-1252, UTF-16). Cf. CONTEXT.md "Import OFX" | ~180 |
| **P12.2.3** | Wrapper exceptions : `ofxparse.OfxParserException` → `IncompatibleAccountError`, `OSError` → `ProviderUnavailableError`, encodage non détecté → `EncodingDetectionError`. Cohérent avec hiérarchie `BankingProviderError` E13 / ADR 0009. Tests | ~120 |
| **P12.2.4** | Mapping fields → `BankTransaction` Pydantic (modèle commun à OFX et Enable Banking) : `external_ref`, `date`, `amount_cents`, `currency`, `payee`, `description`, `fitid` (gardé pour debug mais non utilisé pour dedup). Tests avec OFX 1.x SGML et OFX 2.x XML | ~150 |

---

### S12.3 — Service d'import + dedup hash composite + critères preview

| Phase | Description | Diff |
|---|---|---|
| **P12.3.1** | `banking/service/import_ofx.py` : `analyze(parsed_ofx, internal_account_id) → ImportPreview` qui calcule : count tx, dedup count (lookup hash composite contre `imported_transactions` table), encoding_confidence, fenêtre temporelle (date min/max), montant max, et les 5 critères F04 d'auto-validation. Pas d'écriture en DB | ~250 |
| **P12.3.2** | Table `imported_transactions` : `id`, `account_id`, `import_hash` (sha256 de `(account_id, date, amount, libellé_normalisé)`), `imported_at`, `source` ('ofx'). Unique `import_hash`. Migration `0015_imported_transactions.py` | ~80 |
| **P12.3.3** | `commit(parsed_ofx, internal_account_id, user_overrides=…) → ImportResult` : pour chaque tx non dupliquée, crée une `Transaction` confirmed avec splits standards (split sur le compte source + split sur catégorie "Sans catégorie" — wait, on a banni "Sans catégorie" ! Donc → la transaction est créée en état `planned` plutôt que `confirmed` pour permettre la catégorisation manuelle. Sauf si user_overrides précise une catégorie par défaut). Logger `imported_transactions`. Tests intégration | ~280 |

---

### S12.4 — Routes upload + preview + commit

| Phase | Description | Diff |
|---|---|---|
| **P12.4.1** | Route `POST /imports/ofx/preview` (multipart file) : parse → analyze → retourne `ImportPreview` JSON. Tests httpx avec fixtures OFX | ~150 |
| **P12.4.2** | Route `POST /imports/ofx/commit` : reçoit le `parsed_ofx_token` (ou re-upload), `internal_account_id`, `user_overrides`, applique. Tests | ~180 |
| **P12.4.3** | Route `POST /imports/ofx/link-account` : crée un `BankAccountExternalRef` (utilisé quand la preview montre un compte non lié). Tests | ~100 |

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
| S12.1 (2 phases) | External refs table | 220 | 220 |
| S12.2 (4 phases) | OFXProvider wrapper | 600 | 820 |
| S12.3 (3 phases) | Service import + dedup | 610 | 1430 |
| S12.4 (3 phases) | Routes | 430 | 1860 |
| S12.5 (2 phases) | Fixtures + tests | 280 | 2140 |
| **Total** | **5 stories / 14 phases** | **~2140 lignes** | |

---

## Critères d'acceptation

- [ ] OFX 1.x SGML et OFX 2.x XML tous deux supportés
- [ ] Encoding détecté avec confiance (BOM ou UTF-8 strict) → `encoding_confidence='high'`, sinon `'low'` et preview obligatoire
- [ ] Dedup par hash composite (`account_id`, `date`, `amount`, `libellé_normalisé`) ; FITID jamais utilisé pour dedup
- [ ] Compte OFX non lié → 422 typé `account_not_linked`, route `/link-account` permet d'établir le mapping
- [ ] Pas de création automatique de compte interne — toujours acte utilisateur explicite
- [ ] Transactions importées en état `planned` (catégorisation manuelle exigée pour passer en `confirmed`)
- [ ] Coverage `OFXProvider` ≥ 80%, service import ≥ 75%

---

## Notes pour l'implémenteur

- `ofxparse` est synchrone. Le wrapper exécute le parsing dans un thread executor (`asyncio.to_thread`) pour ne pas bloquer FastAPI event loop sur les gros fichiers (~50 lignes mais en cas de plusieurs MB d'OFX, ça bloquerait).
- Le `parsed_ofx_token` entre `/preview` et `/commit` : on stocke le fichier uploadé dans un dossier temporaire avec un UUID, on retourne le token, le commit le récupère. Cleanup automatique après 30 min ou commit. Pas de stockage long terme.
- Le state `planned` à l'import est conservateur — l'utilisateur doit confirmer chaque tx en y mettant une catégorie. Si trop pénible à l'usage, V1.5 = auto-confirm avec catégorie "À catégoriser" exempte de l'invariant `UncategorizedExpenseError` (mais ça contredit la décision E06).
- Le `libellé_normalisé` du hash composite : `strip + lowercase + retire les préfixes bancaires standard` (cf. CONTEXT.md MatchScorer). Cohérence avec la reconciliation V1.
