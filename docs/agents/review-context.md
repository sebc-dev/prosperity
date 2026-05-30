# Review context gathering

Shared procedure for the `/review-plan` and `/review-code` commands. Both run a
three-agent parallel review (code & architecture, security, tests) and need the
**same** project context assembled first. Gather it once, then hand the relevant
slices to each sub-agent.

## 1. Resolve the story

The story identifier is `SXX.Y` (e.g. `S04.2`).

1. **From the argument** if one was given: it may be the id (`S04.2`), the issue
   number (`75`), or both.
2. **Otherwise infer from the current branch**: `git branch --show-current`
   yields `story/S04.2-admin-audit-log` → story `S04.2`.

Then locate the GitHub issue (titles look like `[S04.2] Audit log admin`):

```
gh issue list --state all --search "S04.2 in:title" --json number,title,labels
```

The epic is `E0X` where `0X` is the story's major number (`S04.2` → `E04`).

## 2. Read these sources

Read what is relevant; skip silently anything that doesn't exist.

- **Story issue + every comment** — the source of truth for acceptance criteria
  and prior decisions:
  `gh issue view <number> --comments`
- **Story plan** — `docs/roadmap/SXX.Y-plan.md` (the detailed implementation plan;
  for `/review-plan` this is the artifact under review).
- **Epic roadmap** — `docs/roadmap/E0X-*.md`, the section for this story. Also the
  epic issue if labelled `epic`.
- **Glossary** — root `CONTEXT.md`. Use its exact vocabulary; flag drift to synonyms
  the glossary tells you to avoid.
- **ADRs** — `docs/adr/`. The issue and plan usually name the relevant ones. Always
  weigh:
  - `0005-directional-import-graph` — module layering (enforced by `.importlinter`).
  - `0015-commit-inside-service-for-security-side-effects` — where commits belong.
  - Security ADRs `0012` (SSE query token), `0013` (2FA/PAT step-up), `0016`
    (JWT aud/iss) when auth/security is touched.
  - Any ADR the diff or plan directly touches.
- **Test strategy** — `docs/Stratégie de tests.md`. Drives the tests agent
  (invariant-focused, TDD on `domain.py`, property-based with Hypothesis,
  substantial testcontainers integration layer, architecture tests — not cosmetic
  coverage).
- **Import contracts** — `.importlinter` for the architecture agent.
- **Runbooks** — `runbooks/` if operational behaviour is in scope.

## 3. Findings format (all agents)

Each agent returns findings with:

- **Severity**: `Bloquant` / `Majeur` / `Mineur` / `Nit`.
- A `file:line` reference (and commit SHA for `/review-code`).
- A concrete, actionable description in French.
- A **per-axis verdict**: `APPROVE` or `CHANGES-REQUESTED`.

`Bloquant` or `Majeur` on any axis ⇒ global verdict `CHANGES-REQUESTED`.

## 4. Output

Post **one consolidated comment in French** on the story issue:

```
gh issue comment <number> --body-file <tmpfile>
```

Structure: global verdict header, then one section per axis (verdict + findings by
severity), then per-axis verdicts table. Also print the synthesis to the terminal.
