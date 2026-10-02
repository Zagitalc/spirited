"""The score components. Each is a pure function returning a value from 0 to 1.

The weights and thresholds here are a starting point, chosen before any road had been
scored. The reference roads (`make evaluate`) are how they get tuned, and each change
belongs in docs/decisions.md.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from spirited.scoring.geometry import Coords, length_m, resample, turning_radii

# Geometry is resampled to this spacing before curvature is measured.
STEP_M = 10.0
# A bend counts only if the radius stays under BEND_RADIUS_M for at least
# MIN_BEND_LENGTH_M of road. Shorter kinks are ignored.
BEND_RADIUS_M = 150.0
MIN_BEND_LENGTH_M = 60.0
# Metres of road inside counted bends, per km, that earns full marks.
FULL_CURVATURE_M_PER_KM = 250.0

# Corridors shorter than this are scored but never recommended on their own.
MIN_CORRIDOR_M = 1000.0

# Below this overall confidence a corridor is not recommended.
MIN_CONFIDENCE = 0.6


class Component(StrEnum):
    CURVATURE = "curvature"
    ROAD_CLASS = "road_class"
    SPEED = "speed"
    JUNCTIONS = "junctions"
    SETTLEMENT = "settlement"
    ELEVATION = "elevation"


WEIGHTS: Mapping[Component, float] = {
    Component.CURVATURE: 0.30,
    Component.ROAD_CLASS: 0.15,
    Component.SPEED: 0.15,
    Component.JUNCTIONS: 0.15,
    Component.SETTLEMENT: 0.15,
    Component.ELEVATION: 0.10,
}


class Ineligible(StrEnum):
    """Why a road gets no score at all."""

    ROAD_CLASS = "road_class"
    SLIP_ROAD = "slip_road"
    SPEED_LIMIT = "speed_limit"
    ROUNDABOUT = "roundabout"


# Residential, living_street and service roads, and motorways, never score. Slip
# roads are links between other roads, not drives in themselves.
SCORED_CLASSES: Mapping[str, float] = {
    "tertiary": 1.0,
    "secondary": 0.9,  # mostly B roads in the UK
    "unclassified": 0.9,  # C roads and named lanes; the filter needs evidence for these
    "primary": 0.5,  # A roads
    "trunk": 0.2,  # primary A roads, mostly busy, many dual carriageway
}

MAX_EXCLUDED_MPH = 30.0


def ineligible_reason(highway: str, mph: float) -> Ineligible | None:
    if highway.endswith("_link"):
        return Ineligible.SLIP_ROAD
    if highway not in SCORED_CLASSES:
        return Ineligible.ROAD_CLASS
    if mph <= MAX_EXCLUDED_MPH + 0.5:
        return Ineligible.SPEED_LIMIT
    return None


def _ramp(value: float, zero_at: float, one_at: float) -> float:
    """0 at `zero_at`, 1 at `one_at`, linear between and clamped outside."""
    t = (value - zero_at) / (one_at - zero_at)
    return float(min(1.0, max(0.0, t)))


# --- curvature ---------------------------------------------------------------


def bend_metres(xy: Coords) -> float:
    """Metres of road inside sustained bends, on geometry already resampled to STEP_M."""
    tight = turning_radii(xy) < BEND_RADIUS_M
    total = 0.0
    run = 0
    for is_tight in [*tight.tolist(), False]:
        if is_tight:
            run += 1
            continue
        if run * STEP_M >= MIN_BEND_LENGTH_M:
            total += run * STEP_M
        run = 0
    return total


def bends_per_km(xy: Coords) -> float:
    """Sustained-bend metres per km of road, for raw (not yet resampled) geometry."""
    total_m = length_m(xy)
    if total_m <= 0:
        return 0.0
    return bend_metres(resample(xy, STEP_M)) / (total_m / 1000)


def curvature_score(bend_m_per_km: float) -> float:
    return _ramp(bend_m_per_km, 0.0, FULL_CURVATURE_M_PER_KM)


# --- road class and speed ----------------------------------------------------


def road_class_score(highway: str) -> float:
    return SCORED_CLASSES.get(highway, 0.0)


def speed_score(mph: float) -> float:
    """60 mph scores 1, 50 mph 0.7, 40 mph 0.3; 70 mph dual carriageways 0.8."""
    return float(np.interp(mph, [30, 40, 50, 60, 70], [0.0, 0.3, 0.7, 1.0, 0.8]))


# --- junctions and settlements -----------------------------------------------


def junction_score(junctions_per_km: float) -> float:
    """Full marks at 2 junctions per km or fewer, nothing at 10 or more."""
    return 1.0 - _ramp(junctions_per_km, 2.0, 10.0)


def settlement_score(share_in_settlement: float) -> float:
    """Full marks when under 10% of the road is in a settlement, nothing above 60%."""
    return 1.0 - _ramp(share_in_settlement, 0.10, 0.60)


# --- elevation ---------------------------------------------------------------

HEIGHT_STEP_M = 50.0
SMOOTHING_WINDOW_M = 300.0
# Climb per km that earns full marks. Steeper roads are not rewarded further, so one
# big hill cannot carry a corridor.
FULL_CLIMB_M_PER_KM = 15.0


def smooth_heights(
    heights: Sequence[float] | NDArray[np.float64], step_m: float = HEIGHT_STEP_M
) -> NDArray[np.float64]:
    """Remove spikes, then average over SMOOTHING_WINDOW_M.

    The terrain data has a resolution of about 30 m and puts cuttings, embankments
    and bridges at the wrong height. A three-point median removes single-sample
    spikes; the moving average then removes the jitter that otherwise adds up to
    hundreds of metres of phantom climbing over a long drive.
    """
    values = np.asarray(heights, dtype=np.float64)
    n = len(values)
    if n < 3:
        return values.copy()
    padded = np.concatenate([[values[0]], values, [values[-1]]])
    median = np.median(np.stack([padded[:-2], padded[1:-1], padded[2:]]), axis=0)
    width = max(1, round(SMOOTHING_WINDOW_M / step_m) | 1)  # odd number of samples
    if width >= n:
        width = n if n % 2 else n - 1
    half = width // 2
    edged = np.concatenate([np.full(half, median[0]), median, np.full(half, median[-1])])
    return np.convolve(edged, np.ones(width) / width, mode="valid")


# Rises and falls smaller than this are treated as noise when adding up climb.
CLIMB_THRESHOLD_M = 3.0


def climb_m(
    heights: Sequence[float] | NDArray[np.float64], threshold_m: float = CLIMB_THRESHOLD_M
) -> float:
    """Metres climbed, ignoring wobbles smaller than `threshold_m` (on smoothed heights)."""
    values = np.asarray(heights, dtype=np.float64)
    if len(values) < 2:
        return 0.0
    climb = 0.0
    reference = float(values[0])
    for value in values[1:].tolist():
        if value - reference >= threshold_m:
            climb += value - reference
            reference = value
        elif reference - value >= threshold_m:
            reference = value
    return climb


def elevation_score(climb_m_per_km: float) -> float:
    return _ramp(climb_m_per_km, 0.0, FULL_CLIMB_M_PER_KM)


# --- narrow lanes ------------------------------------------------------------

# A two-way road narrower than this cannot take two cars side by side at speed.
NARROW_WIDTH_M = 5.0
# Share of the score kept on a road that is entirely narrow. Narrow lanes stay
# routable and scored, but rarely beat a proper road.
NARROW_SCORE_FACTOR = 0.5

# How much an untagged unclassified road counts towards being narrow.
POSSIBLY_NARROW = 0.5

_WIDTH = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m)?\s*$")


def parse_width_m(value: str) -> float | None:
    """A width in metres from `width` or `est_width`; feet and inches are ignored."""
    match = _WIDTH.match(value)
    return float(match.group(1)) if match else None


def narrowness(tags: Mapping[str, str]) -> float:
    """1 when the tags say a two-way road is single track or too narrow to pass, 0.5
    when it is an unclassified road with nothing to say either way, otherwise 0.

    Most lanes carry no width or lanes tag, but in England most single-track roads are
    unclassified, so an untagged unclassified road counts as possibly narrow. One-way
    roads are left out: one lane on each carriageway of a dual road is normal.
    """
    if tags.get("oneway") in ("yes", "1", "-1"):
        return 0.0
    lanes = tags.get("lanes", "")
    widths = [parse_width_m(tags.get(key, "")) for key in ("width", "est_width")]
    known = [w for w in widths if w is not None]
    if lanes == "1" or any(w < NARROW_WIDTH_M for w in known):
        return 1.0
    if (lanes.isdigit() and int(lanes) >= 2) or known:
        return 0.0
    return POSSIBLY_NARROW if tags.get("highway") == "unclassified" else 0.0


def narrow_factor(narrow_share: float) -> float:
    """Multiplier on the score for how narrow a corridor is, from 0 to 1."""
    return 1.0 - (1.0 - NARROW_SCORE_FACTOR) * min(1.0, max(0.0, narrow_share))


# --- combining ---------------------------------------------------------------


@dataclass(frozen=True)
class Part:
    value: float
    confidence: float


def combine(parts: Mapping[Component, Part]) -> tuple[float, float]:
    """The score out of 100 and the overall confidence from 0 to 1."""
    score = sum(WEIGHTS[name] * part.value for name, part in parts.items())
    confidence = sum(WEIGHTS[name] * part.confidence for name, part in parts.items())
    total_weight = sum(WEIGHTS[name] for name in parts)
    return 100 * score / total_weight, confidence / total_weight


def curvature_confidence(mean_node_spacing_m: float) -> float:
    """Sparse geometry can hide bends: full confidence up to 50 m spacing, 0.5 at 200 m.

    The floor is high because a straight road is legitimately drawn with few nodes;
    spacing alone cannot tell a straight road from a carelessly drawn lane.
    """
    return 1.0 - 0.5 * _ramp(mean_node_spacing_m, 50.0, 200.0)
