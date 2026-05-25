"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os

from hypothesis import settings as _hyp_settings

# Profiles consumed by CI: push.yml leaves the default (max_examples=100),
# nightly.yml sets HYPOTHESIS_PROFILE=nightly for the 500-example sweep
# (docs/Stratégie de tests §9.3).
_hyp_settings.register_profile("ci", max_examples=50)
_hyp_settings.register_profile("nightly", max_examples=500)
_hyp_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
