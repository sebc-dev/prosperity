---
phase: 4
slug: categories
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-05
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | JUnit 5 + Testcontainers (backend) / Jasmine + Karma (frontend) |
| **Config file** | `pom.xml` (backend) / `angular.json` (frontend) |
| **Quick run command** | `./mvnw test -pl . -Dtest="*Category*"` |
| **Full suite command** | `./mvnw verify && pnpm test --watch=false` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `./mvnw test -pl . -Dtest="*Category*"`
- **After every plan wave:** Run `./mvnw verify && pnpm test --watch=false`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | CATG-01 | migration | `./mvnw test -Dtest="*Migration*"` | ❌ W0 | ⬜ pending |
| 4-01-02 | 01 | 1 | CATG-01 | unit | `./mvnw test -Dtest="CategoryRepositoryTest"` | ❌ W0 | ⬜ pending |
| 4-01-03 | 01 | 1 | CATG-02 | unit | `./mvnw test -Dtest="CategoryServiceTest"` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 1 | CATG-02 | integration | `./mvnw test -Dtest="CategoryControllerTest"` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 2 | CATG-03 | integration | `./mvnw test -Dtest="TransactionCategoryTest"` | ❌ W0 | ⬜ pending |
| 4-04-01 | 04 | 2 | CATG-04 | component | `pnpm test --watch=false --include="*category*"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/test/java/com/example/prosperity/category/CategoryRepositoryTest.java` — stubs pour CATG-01
- [ ] `src/test/java/com/example/prosperity/category/CategoryServiceTest.java` — stubs pour CATG-01, CATG-02
- [ ] `src/test/java/com/example/prosperity/category/CategoryControllerTest.java` — stubs pour CATG-02
- [ ] `src/test/java/com/example/prosperity/transaction/TransactionCategoryTest.java` — stubs pour CATG-03
- [ ] `src/app/shared/category-selector/category-selector.component.spec.ts` — stubs pour CATG-04

*Wave 0 crée les fichiers de test avec les cas nominaux vides avant l'implémentation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hiérarchie affichée parent > sous-catégorie dans le TreeSelect | CATG-04 | Rendu visuel | Ouvrir le composant, vérifier l'indentation dans le dropdown |
| Catégories système non modifiables/supprimables en UI | CATG-01 | UX interaction | Tenter d'éditer une catégorie `is_system=true`, vérifier le bouton désactivé |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
