"""Plane geometry in metres for a region the size of Berkshire.

Everything is projected onto one flat plane centred on the region (an equirectangular
projection). Across the clip box the scale error is about 2 per cent, which is far
below anything the scores can resolve, and one shared plane lets corridors, villages
and reference roads be compared directly.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from spirited.region import CLIP_BOX

EARTH_RADIUS_M = 6_371_008.8
ORIGIN_LON = (CLIP_BOX.min_lon + CLIP_BOX.max_lon) / 2
ORIGIN_LAT = (CLIP_BOX.min_lat + CLIP_BOX.max_lat) / 2
_M_PER_DEG_LAT = math.pi * EARTH_RADIUS_M / 180
_M_PER_DEG_LON = _M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))

Coords = NDArray[np.float64]
"""An (n, 2) array of points, either (lon, lat) or (x, y) in metres."""


def to_xy(lonlat: Coords) -> Coords:
    lonlat = np.asarray(lonlat, dtype=np.float64).reshape(-1, 2)
    x = (lonlat[:, 0] - ORIGIN_LON) * _M_PER_DEG_LON
    y = (lonlat[:, 1] - ORIGIN_LAT) * _M_PER_DEG_LAT
    return np.column_stack([x, y])


def to_lonlat(xy: Coords) -> Coords:
    xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    lon = xy[:, 0] / _M_PER_DEG_LON + ORIGIN_LON
    lat = xy[:, 1] / _M_PER_DEG_LAT + ORIGIN_LAT
    return np.column_stack([lon, lat])


def segment_lengths(xy: Coords) -> NDArray[np.float64]:
    return np.hypot(*np.diff(xy, axis=0).T) if len(xy) > 1 else np.zeros(0)


def length_m(xy: Coords) -> float:
    return float(segment_lengths(xy).sum())


def points_along_lonlat(lonlat: Coords, count: int) -> list[tuple[float, float]]:
    """`count` points spaced evenly along a line, each in the middle of its share of the
    line (one point is the midpoint), as (lon, lat)."""
    xy = to_xy(lonlat)
    along = np.concatenate([[0.0], np.cumsum(segment_lengths(xy))])
    at = (np.arange(count) + 0.5) / count * along[-1]
    x = np.interp(at, along, xy[:, 0])
    y = np.interp(at, along, xy[:, 1])
    return [(float(lon), float(lat)) for lon, lat in to_lonlat(np.column_stack([x, y]))]


def resample(xy: Coords, step_m: float) -> Coords:
    """Points every `step_m` metres along the line, always including both ends."""
    lengths = segment_lengths(xy)
    keep = np.concatenate([[True], lengths > 0])
    xy, lengths = xy[keep], lengths[lengths > 0]
    if len(xy) < 2:
        return xy.copy()
    along = np.concatenate([[0.0], np.cumsum(lengths)])
    total = float(along[-1])
    stations = np.append(np.arange(0.0, total, step_m), total)
    return np.column_stack(
        [np.interp(stations, along, xy[:, 0]), np.interp(stations, along, xy[:, 1])]
    )


def turning_radii(xy: Coords, span: int = 2) -> NDArray[np.float64]:
    """Radius of the circle through each point and its neighbours `span` steps away.

    Expects evenly spaced points (see `resample`). The first and last `span` points
    have no neighbours on one side and get an infinite radius, as does any straight
    run. Measuring across several steps rather than adjacent points keeps the radius
    from reacting to the odd misplaced node.
    """
    n = len(xy)
    radii = np.full(n, np.inf)
    if n < 2 * span + 1:
        return radii
    a = xy[: n - 2 * span]
    b = xy[span : n - span]
    c = xy[2 * span :]
    ab = np.hypot(*(b - a).T)
    bc = np.hypot(*(c - b).T)
    ca = np.hypot(*(a - c).T)
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    twice_area = np.abs(cross)
    with np.errstate(divide="ignore", invalid="ignore"):
        inner = np.where(twice_area > 1e-9, ab * bc * ca / (2 * twice_area), np.inf)
    radii[span : n - span] = inner
    return radii


def mean_node_spacing_m(xy: Coords) -> float:
    """Average distance between the nodes of the original OSM geometry."""
    lengths = segment_lengths(xy)
    return float(lengths.mean()) if len(lengths) else 0.0
