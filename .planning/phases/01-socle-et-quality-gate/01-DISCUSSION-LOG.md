# Phase 1: Socle et quality gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-21
**Phase:** 01-socle-et-quality-gate
**Areas discussed:** Amorçage des protections, Preuve de la gate, Module canari, Outils hors npm en local

L'utilisateur a demandé une explication pour/contre avec recommandation justifiée pour chaque choix, puis une page de décision. Deux artefacts ont servi de support : « Verrou de la quality gate » (https://claude.ai/artifact/NiMzph6XTZdkD4nirnbND8) et « Preuve et outillage de la gate » (https://claude.ai/artifact/Uk219TgmWkGecxsGPxG8mi). Toutes les recommandations ont été retenues.

---

## Amorçage des protections

| Question | Options | Retenu |
|---|---|---|
| Moment du verrou | A dernier plan · B progressif par check · C dès le 1er plan | A |
| Approbation humaine | A label vérifié par auteur, lié au dernier commit, deny gh labels · B second compte reviewer · C commit d'approbation signé | A |
| Arrêt local de l'agent | A settings.json deny + hook PreToolUse + lefthook · B settings.json seul | A |
| Protection de `.claude/` | A sous-ensemble (settings*.json, CLAUDE.md ; hook dans quality/agent-guard/) · B tout `.claude/**` · C GSD au niveau utilisateur | A |

**User's choice:** recommandations A partout.

---

## Preuve de la gate

| Question | Options | Retenu |
|---|---|---|
| Forme de la preuve | A auto-test à fixtures seul · B vraies PR seules · C hybride | C |
| Quand rejouer l'auto-test | A chaque PR · B PR touchant un chemin protégé + nightly · C nightly seul | B |

## Module canari

| Question | Options | Retenu |
|---|---|---|
| Code canari | A vrai `shared/money` minimal · B module jouet jetable | A |
| Intégration PostgreSQL | A socle de base + méta-tests RLS armés · B table canari jetable | A |

## Outils hors npm en local

| Question | Options | Retenu |
|---|---|---|
| Installation | A mise (`mise.toml` protégé) · B conteneur d'outillage · C CI seule | A |
| Pré-push vs CI | A même commande, profil `push`, checks lourds `ci-only` · B pré-push = gate complète | A |
| Runners CI | A GitHub hébergés · B auto-hébergé homelab | A |

**User's choice:** « je garde toutes tes recommandations ».

## Claude's Discretion

- Découpage exact des plans (le verrou reste le dernier), format des cas d'auto-test et de `gate.json`, parseur shell du hook de garde.

## Deferred Ideas

- Commit d'approbation signé si le modèle de menace évolue.
- Runner auto-hébergé, écarté tant que le dépôt est public.
