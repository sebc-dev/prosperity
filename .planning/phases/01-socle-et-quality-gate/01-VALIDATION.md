---
phase: "1"
slug: "socle-et-quality-gate"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-21"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Vitest 5.1.x (projets `unit` + `integration`), fast-check 4.10.x, StrykerJS 10.1.1 |
| **Config file** | `vitest.config.ts`, `stryker.config.json` (none — Wave 0 installs) |
| **Quick run command** | `pnpm quality --profile push` |
| **Full suite command** | `pnpm quality` (+ `pnpm quality --only selftest`) |
| **Estimated runtime** | ~60 seconds (profil push) ; CI complète ≤ 8-10 min |

---

## Sampling Rate

- **After every task commit:** Run `pnpm quality --profile push` (dès qu'il existe ; avant, la commande de vérification propre à la tâche)
- **After every plan wave:** Run `pnpm quality` + `pnpm quality --only selftest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| *(à remplir depuis les PLAN.md)* | | | | | | | | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Correspondance exigences → tests (depuis 01-RESEARCH.md § Validation Architecture) :

| Req ID | Test Type | Automated Command |
|--------|-----------|-------------------|
| QUAL-01 | unit + e2e | `pnpm vitest run quality/run.test.ts` ; PR réelle (D-07b) |
| QUAL-02 | selftest | `pnpm quality --only selftest --case lint-*` |
| QUAL-03 | selftest | `pnpm quality --only selftest --case arch-*,deadcode-*,dup-*` |
| QUAL-04 | selftest | `pnpm quality --only selftest --case sec-*` |
| QUAL-05 | unit + selftest | `pnpm vitest run --project unit --coverage` ; `pnpm stryker run` |
| QUAL-06 | selftest | `pnpm quality --only selftest --case integrity-*` |
| QUAL-07 | manuel guidé + e2e | tentative d'édition en session agent ; `gh api …/rulesets` |
| QUAL-08 | integration + selftest | `pnpm vitest run --project integration` |
| QUAL-09 | selftest + PR réelle | `pnpm quality --only selftest --case deps-*` |

---

## Wave 0 Requirements

- [ ] `quality/` (runner, registre, rapport, intégrité, approbations, deps-guard, compteur) et `quality/selftest/` (cas + runner worktree)
- [ ] `vitest.config.ts`, `stryker.config.json`, `eslint.config.mjs`, `tsconfig.json`, `.dependency-cruiser.cjs`, `knip.json`, `.jscpd.json`, `.gitleaks.toml`, `biome.json`, `lefthook.yml`
- [ ] `test/` : `globalSetup` Testcontainers, méta-tests (RLS `owner_member_id`, rôle app sans DDL)
- [ ] `src/shared/money/` + tests (exemples + propriétés), `src/db/`, `db/migrations/0001_foundation.sql`
- [ ] `mise install` puis `pnpm install --frozen-lockfile`
- [ ] Mesure de stabilité Stryker (Q2) : 20 exécutions du canari

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Le check requis `quality` bloque le merge sur `main` | QUAL-01, QUAL-07 | Seul GitHub le prouve (ruleset) | PR réelle rouge → merge refusé |
| Label posé par `sebc-dev` accepté, par un autre acteur refusé, retiré au push suivant | QUAL-06 | Événements de PR GitHub réels | Passage manuel guidé D-07b |
| Dépendance ajoutée sans `deps-approved` bloquée | QUAL-09 | PR réelle | Passage manuel guidé D-07b |
| Édition d'un fichier de la gate par l'agent refusée | QUAL-07 | Session agent réelle | Tentative d'Edit/Bash en session Claude Code |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
