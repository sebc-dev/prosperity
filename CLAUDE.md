## Cycle spec-driven (OpenSpec + `scd-spec-dev`)

Le projet est piloté par **OpenSpec** (`openspec/`) accordé au schéma custom **`scd`** (`openspec/schemas/scd/`), via le plugin **`scd-spec-dev`**. Le contexte injecté aux artefacts vit dans `openspec/config.yaml` (pointe vers les docs durables : `docs/roadmap/`, `docs/adr/`, `runbooks/ci.md`, `docs/Stratégie de tests.md`, `docs/ui/`).

Cadrage durable = `docs/roadmap/` (epics `EXX-*.md`, stories `SXX.Y` en sections ; le statut est porté par la ligne `> **Statut**` de l'epic et le tableau de `docs/roadmap/README.md`, les stories sont synchronisées en issues GitHub via `to-issues`). **Un change sert une STORY** : `proposal.md` la backréférence (`EPIC-XX / STORY-SXX.Y`), et l'archive du change clôt la story (issue fermée, statut de l'epic mis à jour).

Cycle : **cadrage durable** → **change** (`/opsx:propose`) → **tickets** (`/scd-spec-dev:tickets`, tranches verticales, un `**Vérif :**` par ticket) → **implémentation** un ticket à la fois (`/scd-spec-dev:run <NN>`, une PR par ticket) → **archive** (`/opsx:archive`). La rigueur tient dans la **review 8 dimensions en contexte frais**, pas dans des hooks de session. **On n'appelle JAMAIS `/opsx:apply`** : `run` prend le relais sur les tickets. `/scd-spec-dev:status` pour l'état.

## Agent skills

### Issue tracker

Issues and PRDs live in GitHub Issues (`sebc-dev/prosperity`); skills use the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five-label vocabulary, defaults unchanged (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` at the root (glossary + domain rules) and system-wide ADRs in `docs/adr/`. There is no context map and no per-context glossary. See `docs/agents/domain.md`.
