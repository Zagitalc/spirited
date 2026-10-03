"""The car costing profile sent with every Valhalla request.

The extract filter is the real safety rule (see spirited.roadfilter); these options
are a second line of defence and the place for routing preferences. They are kept
here, not in Valhalla's server config, so every request states them explicitly.
"""

from __future__ import annotations

from typing import Any

COSTING = "auto"

# Valhalla auto costing options. Values are documented in docs/decisions.md.
AUTO_OPTIONS: dict[str, Any] = {
    "use_tracks": 0.0,
    "exclude_unpaved": True,
    "use_living_streets": 0.0,
    "service_penalty": 300,
    "use_ferry": 0.0,
    "ignore_access": False,
    "use_highways": 0.0,
}


def costing_options() -> dict[str, dict[str, Any]]:
    """A fresh copy, so callers can adjust options without changing the profile."""
    return {COSTING: dict(AUTO_OPTIONS)}
