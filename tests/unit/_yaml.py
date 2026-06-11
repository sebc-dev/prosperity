"""Test-only YAML loader that understands PowerSync's `!env` tag.

PowerSync config files use a custom `!env PS_FOO` YAML tag for env-var
substitution. `yaml.safe_load` raises on unknown tags, so the manifest tests
load through `load()` here, which resolves `!env PS_FOO` to the marker string
``"!env:PS_FOO"`` instead of crashing.

This validates YAML *syntax* and lets a test assert that every referenced PS_*
variable is declared in `.env.example` (catching a `!env PS_TYPO`). It does NOT
resolve real values — semantics (valid URIs, a reachable service) are covered by
the nightly smoke against a live PowerSync Service.

Prefixed with `_` so pytest does not collect it as a test module.
"""

from __future__ import annotations

from typing import Any

import yaml

ENV_PREFIX = "!env:"


class EnvTagLoader(yaml.SafeLoader):
    """SafeLoader extended with a no-op `!env` constructor."""


def _construct_env(loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode) -> str:
    return f"{ENV_PREFIX}{loader.construct_scalar(node)}"


EnvTagLoader.add_constructor("!env", _construct_env)


def load(text: str) -> Any:
    """Parse YAML text, tolerating `!env` tags (resolved to marker strings)."""
    return yaml.load(text, Loader=EnvTagLoader)


def env_refs(value: Any) -> set[str]:
    """Collect every PS_* name referenced via `!env` anywhere in `value`."""
    found: set[str] = set()
    if isinstance(value, str):
        if value.startswith(ENV_PREFIX):
            found.add(value[len(ENV_PREFIX) :])
    elif isinstance(value, dict):
        for v in value.values():  # pyright: ignore[reportUnknownVariableType]
            found |= env_refs(v)
    elif isinstance(value, list):
        for v in value:  # pyright: ignore[reportUnknownVariableType]
            found |= env_refs(v)
    return found
