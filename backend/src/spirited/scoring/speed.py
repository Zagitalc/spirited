"""UK speed limits from OSM tags, inferred when the tags are missing.

Roads at 30 mph or below never score, so the speed limit decides which roads are
considered at all. Many minor roads carry no `maxspeed` tag, so the limit is inferred
from other evidence in a fixed order, and every value records where it came from.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

KMH_PER_MPH = 1.609344
NATIONAL_SINGLE_MPH = 60
NATIONAL_DUAL_MPH = 70
BUILT_UP_MPH = 30


class SpeedSource(StrEnum):
    TAGGED = "tagged"
    NATIONAL_TAG = "national_tag"
    LIT = "lit"
    SETTLEMENT = "settlement"
    ASSUMED = "assumed"


# How far each source can be trusted, from 0 to 1.
SOURCE_CONFIDENCE = {
    SpeedSource.TAGGED: 1.0,
    SpeedSource.NATIONAL_TAG: 1.0,
    SpeedSource.LIT: 0.6,
    SpeedSource.SETTLEMENT: 0.6,
    SpeedSource.ASSUMED: 0.3,
}


@dataclass(frozen=True)
class SpeedLimit:
    mph: float
    source: SpeedSource

    @property
    def confidence(self) -> float:
        return SOURCE_CONFIDENCE[self.source]


_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?\s*$")

# Values of maxspeed, maxspeed:type and source:maxspeed that mean a known UK limit.
_TYPE_LIMITS = {
    "national": None,  # single or dual depends on the road; see _national
    "gb:national": None,
    "gb:nsl_single": NATIONAL_SINGLE_MPH,
    "uk:nsl_single": NATIONAL_SINGLE_MPH,
    "gb:nsl_dual": NATIONAL_DUAL_MPH,
    "uk:nsl_dual": NATIONAL_DUAL_MPH,
    "gb:motorway": NATIONAL_DUAL_MPH,
    "uk:motorway": NATIONAL_DUAL_MPH,
    "gb:zone20": 20,
    "uk:zone20": 20,
    "gb:zone30": 30,
    "uk:zone30": 30,
    "gb:urban": BUILT_UP_MPH,
    "uk:urban": BUILT_UP_MPH,
}


def parse_maxspeed(value: str) -> float | None:
    """A `maxspeed` value in mph, or None if it is not a number.

    A bare number is km/h, as the OSM wiki defines it. A list such as
    "30 mph;20 mph" (different limits by time or lane) takes the lowest, because a
    road that is sometimes 20 mph should not be treated as a 30 mph road.
    """
    speeds = []
    for part in value.split(";"):
        match = _NUMBER.match(part)
        if not match:
            return None
        number, unit = float(match.group(1)), match.group(2)
        speeds.append(number if unit == "mph" else number / KMH_PER_MPH)
    return min(speeds) if speeds else None


def _is_dual(tags: Mapping[str, str]) -> bool:
    highway = tags.get("highway", "")
    return highway.startswith("motorway") or tags.get("dual_carriageway") == "yes"


def _national(tags: Mapping[str, str]) -> float:
    return NATIONAL_DUAL_MPH if _is_dual(tags) else NATIONAL_SINGLE_MPH


def _from_type(value: str | None, tags: Mapping[str, str]) -> float | None:
    if value is None:
        return None
    key = value.strip().lower()
    if key not in _TYPE_LIMITS:
        return None
    limit = _TYPE_LIMITS[key]
    return _national(tags) if limit is None else limit


def speed_limit(tags: Mapping[str, str], in_settlement: bool) -> SpeedLimit:
    """The best estimate of a way's speed limit, with where it came from."""
    maxspeed = tags.get("maxspeed")
    if maxspeed is not None:
        mph = parse_maxspeed(maxspeed)
        if mph is not None:
            return SpeedLimit(mph, SpeedSource.TAGGED)
        typed = _from_type(maxspeed, tags)
        if typed is not None:
            return SpeedLimit(typed, SpeedSource.NATIONAL_TAG)

    for key in ("maxspeed:type", "source:maxspeed"):
        typed = _from_type(tags.get(key), tags)
        if typed is not None:
            return SpeedLimit(typed, SpeedSource.NATIONAL_TAG)

    if tags.get("highway", "").startswith("motorway"):
        return SpeedLimit(NATIONAL_DUAL_MPH, SpeedSource.NATIONAL_TAG)
    # In the UK, a road with street lights is 30 mph unless signs say otherwise. Trunk
    # roads are left out because lit dual carriageways near towns are common and are
    # usually signed higher.
    if tags.get("lit") == "yes" and not tags.get("highway", "").startswith("trunk"):
        return SpeedLimit(BUILT_UP_MPH, SpeedSource.LIT)
    if in_settlement:
        return SpeedLimit(BUILT_UP_MPH, SpeedSource.SETTLEMENT)
    return SpeedLimit(_national(tags), SpeedSource.ASSUMED)
