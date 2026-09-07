## Cycle spec-driven (OpenSpec + `scd-spec-dev`)

Le projet est piloté par **OpenSpec** (`openspec/`) accordé au schéma custom **`scd`** (`openspec/schemas/scd/`), via le plugin **`scd-spec-dev`**. Le contexte injecté aux artefacts vit dans `openspec/config.yaml` (pointe vers les docs durables : `docs/roadmap/`, `docs/adr/`, `runbooks/ci.md`, `docs/Stratégie de tests.md`, `docs/ui/`).

Cycle : **cadrage durable** → **change** (`/opsx:propose`) → **tickets** (`/scd-spec-dev:tickets`, tranches verticales, un `**Vérif :**` par ticket) → **implémentation** un ticket à la fois (`/scd-spec-dev:run <NN>`, une PR par ticket) → **archive** (`/opsx:archive`). La rigueur tient dans la **review 8 dimensions en contexte frais**, pas dans des hooks de session. **On n'appelle JAMAIS `/opsx:apply`** : `run` prend le relais sur les tickets. `/scd-spec-dev:status` pour l'état.

## Agent skills

### Issue tracker

Issues and PRDs live in GitHub Issues (`sebc-dev/prosperity`); skills use the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five-label vocabulary, defaults unchanged (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context: `CONTEXT-MAP.md` at the root points to per-context `CONTEXT.md` files; per-context `docs/adr/` lives next to each. See `docs/agents/domain.md`.
