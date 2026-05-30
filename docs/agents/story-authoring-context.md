# Story authoring context gathering

Shared procedure for the `/create-stories` and `/create-plan` commands. Both turn a
roadmap artefact (an epic, or a single story) into a GitHub deliverable — story
issues, or a story implementation plan. They need the **same** project context
assembled first: the roadmap source of truth, the glossary, the ADRs, the test
strategy, the import contracts, and everything already decided on neighbouring
issues. Gather it once, then write.

Everything the commands produce is **in French** (project language: `CONTEXT.md`,
roadmap, issues are all French) and uses the glossary's exact vocabulary.

## 1. Resolve the target

- **Epic** id is `EXX` (e.g. `E04`); **story** id is `SXX.Y` (e.g. `S04.2`);
  **phase** id is `PXX.Y.Z`. The story `S04.2` belongs to epic `E04`.
- **From the argument** if given: it may be the id (`E04` / `S04.2`), the GitHub
  issue number, or both.
- **Otherwise infer from the current branch**: `git branch --show-current` yields
  e.g. `story/S04.2-...` → `S04.2`.

Locate the GitHub issue (`gh` infers the repo from `git remote`):

```
# Epic — titles look like "[E04] RBAC + invitations", label `epic`
gh issue list --state all --label epic --search "E04 in:title" --json number,title,labels

# Story — titles look like "[S04.2] Audit log admin"
gh issue list --state all --search "S04.2 in:title" --json number,title,labels
```

## 2. Read these sources

Read what is relevant; skip silently anything that doesn't exist (don't flag the
absence, don't propose creating it). See `docs/agents/issue-tracker.md` for the
`gh` conventions and `docs/agents/domain.md` for how to consume domain docs.

- **Roadmap conventions** — `docs/roadmap/README.md`: the Epic/Story/Phase
  hierarchy, the **atomicity rules per phase** (single responsibility, branch stays
  green, no refactor+feature+test mix, test-first on `domain.py`, DB migration = own
  phase, new ADR = own phase before its dependant, inline docs in the same PR), the
  naming convention (`EXX` / `SXX.Y` / `PXX.Y.Z`, branch `SXX.Y-slug`), and the
  status vocabulary (`not started` / `in progress` / `done` / `blocked`).
- **Epic roadmap file** — `docs/roadmap/EXX-*.md`. This is the **source of truth**
  for the découpage: objective, the per-story breakdown (table of phases with diff
  estimates), récapitulatif, acceptance criteria, implementer notes. The `> ` header
  carries `Dépend de` / `Bloque` / `ADRs activés`.
- **Epic issue + comments** — the GitHub `[EXX]` issue (label `epic`); its body
  mirrors the epic file, its comments may carry later decisions:
  `gh issue view <number> --comments`.
- **Story issues + every comment** — for the stories of this epic
  (`[SXX.Y]` titles). Two reasons: (a) **avoid duplicates** — a story already filed
  must not be re-created; (b) **format consistency** — read a well-formed recent
  story issue as the template (Objectif / Livrable observable / Phases atomiques /
  Critères d'acceptation / Notes pour l'implémenteur). Comments often hold
  multi-agent review decisions that supersede the roadmap file — treat them as
  authoritative.
- **Dependency & predecessor work** — the epics this one `Dépend de` (their files +
  issues) and the **previous stories in the same epic** (their issues, their review
  comments, and any historical plan: a `docs/roadmap/SXX.Y-plan.md` file or a plan
  posted as an issue comment). They establish the existing primitives, public APIs,
  and decisions the new work must build on.
- **Glossary** — root `CONTEXT.md`. Use its exact vocabulary; flag drift to synonyms
  it tells you to avoid. (Per `docs/agents/domain.md`, also read any per-context
  `CONTEXT.md` / `CONTEXT-MAP.md` if they exist.)
- **ADRs** — `docs/adr/`. The epic/story usually names the relevant ones. Always
  weigh:
  - `0005-directional-import-graph` — module layering, enforced by `.importlinter`.
  - `0015-commit-inside-service-for-security-side-effects` — where commits belong.
  - Security ADRs `0012` (SSE query token), `0013` (2FA/PAT step-up), `0016`
    (JWT aud/iss) when auth/security is in scope.
  - Any ADR the epic/story directly touches. A **new ADR** is its own phase, placed
    before the phase that relies on it.
- **Test strategy** — `docs/Stratégie de tests.md`: invariant-focused, TDD on
  `domain.py`, property-based with Hypothesis where it counts, substantial
  testcontainers integration layer, architecture tests — not cosmetic coverage. This
  drives the per-phase test cases.
- **Import contracts** — `.importlinter`: the contracts (and their existing
  exceptions) any new module placement must respect. A plan/story that needs a new
  cross-module import must say where the code goes so no new exception is required.
- **Runbooks** — `runbooks/` if operational behaviour is in scope.

## 3. Reconcile roadmap vs. current context

The roadmap file is the **baseline**, not gospel. Context drifts after it was
written: new ADRs land, import contracts tighten, and prior-story review comments
record corrections (e.g. S04.1 moved the RBAC Depends out of `shared/` because
import-linter contract #3 forbids `shared → modules.*`). When the baseline conflicts
with what the ADRs / contracts / issue comments now say:

- Prefer the **current** decision; treat issue review comments as authoritative over
  the roadmap file.
- **Surface the delta explicitly** rather than silently overriding — note it in the
  output and, when the roadmap file itself is now wrong, update `docs/roadmap/EXX-*.md`
  in the same change (and say so), as the `E04 §S04.1` note demands.
- Respect the atomicity rules from §README when re-shaping phases.

## 4. Vocabulary & quality bar

- French, glossary vocabulary, ADR-aware. Flag any contradiction with an existing ADR
  (`docs/agents/domain.md`): _"Contredit l'ADR-XXXX — mais à rouvrir parce que…"_.
- The bar is **grilling-resistant**: every structural decision justified, every test
  case named, every import-linter contract accounted for. No "TODO décider plus tard".
