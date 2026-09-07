# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo is **single-context**: one `CONTEXT.md` at the root carries the glossary and the domain rules, and system-wide architectural decisions live in `docs/adr/`. There is no context map and no per-context glossary — do not look for them, do not create them.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the glossary (`## Language`) and the domain rules. Read the sections relevant to the topic.
- **`docs/adr/`** at the root — system-wide architectural decisions (Nygard format). `docs/architecture.md` lists the invariants they impose.

If a section you expect is missing, **proceed silently**. Don't flag its absence; don't suggest creating it upfront. The producer skill (`/grill-with-docs`) extends `CONTEXT.md` lazily when terms or decisions actually get resolved.

## File structure

```
/
├── CONTEXT.md                         ← glossary + domain rules (single context)
├── docs/adr/                          ← system-wide decisions
└── docs/architecture.md               ← invariants derived from the ADRs
```

If the repo ever splits into bounded contexts, this file is where the layout changes — `CLAUDE.md` › `### Domain docs` must be updated in the same PR.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids (`_Avoid_` lines).

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
