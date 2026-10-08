"""Generate circular drives from the road scores and a Valhalla router.

Valhalla knows nothing about the scores, so the only lever is the choice of waypoints.
The generator picks the middles of well-scored corridors that lie within reach, routes
start -> waypoints -> start, maps each route back to corridors through its OSM way ids,
and keeps the loops whose roads pass the checks in `LoopConfig`.
"""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from itertools import pairwise, permutations, zip_longest
from statistics import median
from typing import NamedTuple, Protocol

import numpy as np
import shapely

from spirited.loops.config import LoopConfig
from spirited.region import CLIP_BOX
from spirited.routing.client import Edge, Route, ValhallaError
from spirited.routing.polyline import LatLon
from spirited.scoring import components as c
from spirited.scoring.geometry import to_xy
from spirited.scoring.store import ScoreStore


class Router(Protocol):
    """What the generator needs from Valhalla (ValhallaClient provides all of it)."""

    def isochrone(self, start: LatLon, minutes: float) -> list[LatLon]: ...

    def matrix(self, points: list[LatLon]) -> list[list[float | None]]: ...

    def route(self, points: list[LatLon], avoid: Sequence[LatLon] = ()) -> Route: ...

    def edges(self, route: Route) -> list[Edge]: ...


# Points of score lost per unit of relative time error (a loop 10% off loses 2.5 points).
TIME_PENALTY = 25.0


class OutsideRegion(ValueError):
    """The start is too close to, or beyond, the edge of the data."""


class Group(StrEnum):
    RECOMMENDED = "recommended"
    NOT_RECOMMENDED = "not_recommended"
    BUILT_UP = "built_up"


# Roads Stage 2 leaves unscored because they are part of getting through a place.
_BUILT_UP_REASONS = {
    c.Ineligible.SPEED_LIMIT.value,
    c.Ineligible.ROAD_CLASS.value,
    c.Ineligible.SLIP_ROAD.value,
    c.Ineligible.ROUNDABOUT.value,
}


def classify(row: sqlite3.Row | None) -> Group:
    """Which group a corridor falls in. A way the scores do not know counts against a loop."""
    if row is None:
        return Group.NOT_RECOMMENDED
    reason = row["ineligible"]
    if reason is None:
        return Group.RECOMMENDED if row["confidence"] >= c.MIN_CONFIDENCE else Group.NOT_RECOMMENDED
    return Group.BUILT_UP if reason in _BUILT_UP_REASONS else Group.NOT_RECOMMENDED


@dataclass(frozen=True)
class Segment:
    from_km: float
    to_km: float
    road: str
    group: Group
    # The corridor's score, for recommended roads only.
    score: float | None


@dataclass(frozen=True)
class Loop:
    waypoints: tuple[LatLon, ...]
    distance_km: float
    duration_min: float
    score: float
    shares: dict[Group, float]
    reuse_share: float
    points: tuple[LatLon, ...] = field(repr=False)
    segments: tuple[Segment, ...] = field(repr=False)
    edge_keys: frozenset[tuple[object, ...]] = field(repr=False)
    warnings: tuple[str, ...] = ()


@dataclass
class LoopResult:
    loops: list[Loop] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    candidates_tried: int = 0
    rejected: Counter[str] = field(default_factory=Counter)
    # Routed time over requested time, one per routed candidate, and the check each
    # time-rejected candidate would have failed next. The time check comes first, so
    # without this a run of "wrong time" hides whether the other limits are too strict.
    time_ratios: list[float] = field(default_factory=list)
    also_fails: Counter[str] = field(default_factory=Counter)
    # Routed time over the matrix's estimate for the same candidate.
    detour_ratios: list[float] = field(default_factory=list)


REJECTION_TEXT = {
    "motorway": "used a motorway",
    "time": "took the wrong time",
    "edge": "ran too close to the edge of the data",
    "recommended": "had too little recommended road",
    "not_recommended": "had too much road we cannot vouch for",
    "run": "had a long stretch of road we cannot vouch for",
    "built_up": "spent too long in built-up areas",
    "reuse": "repeated too much of its own road",
    "retrace": "turned back on itself down a road",
    "duplicate": "was too like a better loop",
    "route": "could not be routed",
}


# --- evaluating one routed loop --------------------------------------------------


def _inside_data(points: Iterable[LatLon], margin: float) -> bool:
    return all(
        CLIP_BOX.min_lon + margin <= lon <= CLIP_BOX.max_lon - margin
        and CLIP_BOX.min_lat + margin <= lat <= CLIP_BOX.max_lat - margin
        for lat, lon in points
    )


def _longest_retrace_km(
    points: Sequence[LatLon], exempt_km: float, step_m: float = 10.0, near_m: float = 12.0
) -> float:
    """The longest stretch of the route that runs back over road it has already driven.

    This looks at the shape of the route, not at the graph edges: a waypoint in the middle
    of an edge splits it into two partial edges, and the edge lists then no longer show that
    the road was driven twice. A point counts as retraced when an earlier part of the route
    passed within `near_m` of it going the opposite way. The last `exempt_km` is not held
    against the loop, because a start on a dead-end road has to come back out of it.
    """
    if len(points) < 2:
        return 0.0
    xy = to_xy(np.array([[lon, lat] for lat, lon in points]))
    fine: list[tuple[float, float, float, float, float]] = []  # x, y, along, ux, uy
    along = 0.0
    for a, b in pairwise(xy):
        length = float(np.hypot(*(b - a)))
        if length < 1e-6:
            continue
        ux, uy = (b - a) / length
        for k in range(max(1, math.ceil(length / step_m))):
            t = k * length / max(1, math.ceil(length / step_m))
            fine.append((a[0] + ux * t, a[1] + uy * t, along + t, ux, uy))
        along += length
    cells: dict[tuple[int, int], list[int]] = {}
    longest = run = gap = 0.0
    last_along = 0.0
    limit = along - exempt_km * 1000
    for i, (x, y, at, ux, uy) in enumerate(fine):
        cx, cy = int(x // near_m), int(y // near_m)
        back = any(
            at - fine[j][2] > 3 * step_m
            and math.hypot(fine[j][0] - x, fine[j][1] - y) <= near_m
            and fine[j][3] * ux + fine[j][4] * uy < -0.7
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for j in cells.get((cx + dx, cy + dy), ())
        )
        cells.setdefault((cx, cy), []).append(i)
        if at > limit:
            break
        step = at - last_along
        last_along = at
        if back:
            run += step + gap
            gap = 0.0
            longest = max(longest, run)
        else:
            gap += step
            if gap > 4 * step_m:
                run = gap = 0.0
    return longest / 1000


def evaluate_route(
    route: Route,
    edges: Sequence[Edge],
    waypoints: Sequence[LatLon],
    store: ScoreStore,
    minutes: float,
    config: LoopConfig,
) -> Loop | str:
    """The loop a route makes, or the reason it is not acceptable (a key of REJECTION_TEXT)."""
    total_km = sum(edge.length_km for edge in edges)
    if total_km <= 0:
        return "route"
    rows = store.corridors_for_ways(edge.way_id for edge in edges)
    if any(str(row["highway"]).startswith("motorway") for row in rows.values()):
        return "motorway"
    duration = route.duration_min / config.speed_factor
    if abs(duration - minutes) > config.tolerance * minutes:
        return "time"
    if not _inside_data(route.points, config.edge_margin_deg):
        return "edge"

    km = dict.fromkeys(Group, 0.0)
    score_km = 0.0
    longest_run = run = 0.0
    seen: set[tuple[object, ...]] = set()
    reused_km = 0.0
    segments: list[Segment] = []
    along = 0.0
    last_key: tuple[int | None, Group] | None = None
    free_km = 0.0  # built-up road near the start or the end, not held against the loop
    retrace = longest_retrace = 0.0
    for edge in edges:
        row = rows.get(edge.way_id)
        group = classify(row)
        km[group] += edge.length_km
        if group is Group.BUILT_UP:
            end = along + edge.length_km
            allowance = config.town_allowance_km
            free_km += max(0.0, min(end, allowance) - along)  # the way out
            free_km += max(0.0, end - max(along, total_km - allowance))  # the way back
        if group is Group.RECOMMENDED and row is not None:
            score_km += row["score"] * edge.length_km
        run = run + edge.length_km if group is Group.NOT_RECOMMENDED else 0.0
        longest_run = max(longest_run, run)
        if edge.key in seen:
            reused_km += edge.length_km
            if along + edge.length_km <= total_km - config.town_allowance_km:
                retrace += edge.length_km
                longest_retrace = max(longest_retrace, retrace)
        else:
            retrace = 0.0
        seen.add(edge.key)

        key = (None if row is None else int(row["id"]), group)
        if key == last_key and segments:
            last = segments[-1]
            segments[-1] = Segment(
                last.from_km, along + edge.length_km, last.road, group, last.score
            )
        else:
            road = ""
            if row is not None:
                road = row["label"] or ""
            road = road or " / ".join(edge.names) or "(unnamed)"
            score = (
                round(row["score"], 1) if row is not None and group is Group.RECOMMENDED else None
            )
            segments.append(Segment(along, along + edge.length_km, road, group, score))
        last_key = key
        along += edge.length_km

    shares = {group: value / total_km for group, value in km.items()}
    reuse = reused_km / total_km
    # The limits are measured on the loop without its way out of town and back.
    counted_km = max(total_km - free_km, 1e-9)
    counted = {group: value / counted_km for group, value in km.items()}
    counted[Group.BUILT_UP] = (km[Group.BUILT_UP] - free_km) / counted_km
    if counted[Group.RECOMMENDED] < config.min_recommended_share:
        return "recommended"
    if counted[Group.NOT_RECOMMENDED] > config.max_not_recommended_share:
        return "not_recommended"
    if longest_run > config.max_not_recommended_run_km:
        return "run"
    if counted[Group.BUILT_UP] > config.max_built_up_share:
        return "built_up"
    if reuse > config.max_reuse_share:
        return "reuse"
    retraced = _longest_retrace_km(route.points, config.town_allowance_km)
    if max(longest_retrace, retraced) > config.max_retrace_run_km:
        return "retrace"

    warnings = []
    if shares[Group.NOT_RECOMMENDED] >= 0.05:
        warnings.append(
            f"{shares[Group.NOT_RECOMMENDED]:.0%} of this loop is on roads we cannot vouch for"
        )
    if reuse >= 0.05:
        warnings.append(f"{reuse:.0%} of this loop repeats a road it has already used")
    return Loop(
        waypoints=tuple(waypoints),
        distance_km=route.distance_km,
        duration_min=duration,
        score=score_km / total_km,
        shares=shares,
        reuse_share=reuse,
        points=route.points,
        segments=tuple(segments),
        edge_keys=frozenset(seen),
        warnings=tuple(warnings),
    )


# --- choosing candidates ---------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    corridor_id: int
    point: LatLon
    score: float
    length_m: float
    bearing: float  # degrees clockwise from north, seen from the start


def _bearing(start_xy: np.ndarray, xy: np.ndarray) -> float:
    dx, dy = xy[0] - start_xy[0], xy[1] - start_xy[1]
    return math.degrees(math.atan2(dx, dy)) % 360


def _gap(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def choose_anchors(
    start: LatLon, outline: Sequence[LatLon], store: ScoreStore, config: LoopConfig
) -> list[Anchor]:
    """Well-scored corridor midpoints inside the isochrone, spread around the start."""
    polygon = shapely.Polygon([(lon, lat) for lat, lon in outline])
    if not polygon.is_valid:
        polygon = shapely.make_valid(polygon)
    shapely.prepare(polygon)
    min_lon, min_lat, max_lon, max_lat = polygon.bounds
    rows = store.anchors((min_lon, min_lat, max_lon, max_lat), config.anchor_min_length_m)
    start_xy = to_xy(np.array([[start[1], start[0]]]))[0]
    found: list[Anchor] = []
    for row in rows:
        if not shapely.contains_xy(polygon, row["lon"], row["lat"]):
            continue
        xy = to_xy(np.array([[row["lon"], row["lat"]]]))[0]
        if float(np.hypot(*(xy - start_xy))) < config.anchor_min_separation_m:
            continue  # too near the start to add a stretch worth driving
        found.append(
            Anchor(
                row["corridor_id"],
                (row["lat"], row["lon"]),
                row["score"],
                row["length_m"],
                _bearing(start_xy, xy),
            )
        )

    # Best anchor first within each 45-degree sector, taken in turn so the loop can go anywhere.
    sectors: list[list[Anchor]] = [[] for _ in range(8)]
    for anchor in found:  # already best first
        sectors[int(anchor.bearing // 45) % 8].append(anchor)
    chosen: list[Anchor] = []
    chosen_xy: list[np.ndarray] = []
    per_corridor: Counter[int] = Counter()
    depth = 0
    while len(chosen) < config.max_anchors and any(depth < len(s) for s in sectors):
        for sector in sectors:
            for anchor in sector[depth : depth + 1]:
                xy = to_xy(np.array([[anchor.point[1], anchor.point[0]]]))[0]
                if per_corridor[anchor.corridor_id] < config.max_anchors_per_corridor and all(
                    float(np.hypot(*(xy - other))) >= config.anchor_min_separation_m
                    for other in chosen_xy
                ):
                    per_corridor[anchor.corridor_id] += 1
                    chosen.append(anchor)
                    chosen_xy.append(xy)
                    if len(chosen) >= config.max_anchors:
                        break
            if len(chosen) >= config.max_anchors:
                break
        depth += 1
    return chosen


class Plan(NamedTuple):
    order: tuple[int, ...]  # indices into the anchors, in driving order
    estimate_s: float  # the matrix's time for the loop, before any detours


def plan_candidates(
    times: Sequence[Sequence[float | None]],
    anchors: Sequence[Anchor],
    target_s: float,
    config: LoopConfig,
    scale: float = 1.0,
) -> list[Plan]:
    """Plans worth routing, best first.

    `times[0]` is the start and `times[i + 1]` is anchor i. A candidate's time is
    estimated from the matrix and must be near the target (the window is wide, since the
    detours routing adds are not known yet). Among those, loops through better-scored
    roads come first, less a penalty for missing the target, judged both at face value
    and once `scale` allows for detours, and the two orders are interleaved. Loops through
    the same set of anchors count once and loops that mostly share anchors with a better
    one are dropped.
    """

    def leg(a: int, b: int) -> float | None:
        return times[a][b]

    sizes = [2, 3] if target_s / 60 >= config.three_waypoints_from_min else [2]
    # Two rankings, tried in turn: one expects routing to add `scale` to the estimate, the
    # other takes the estimate at face value. Detours differ a lot from loop to loop and
    # the loops that pass are often the ones with almost none, so neither ranking alone
    # is safe to rely on.
    rankings: list[dict[frozenset[int], tuple[float, Plan]]] = [{}, {}]
    for size in sizes:
        for order in permutations(range(len(anchors)), size):
            stops = [0, *(i + 1 for i in order), 0]
            legs = [leg(a, b) for a, b in pairwise(stops)]
            if any(t is None for t in legs):
                continue
            estimate = sum(t for t in legs if t is not None)
            if not -config.planning_below <= estimate / target_s - 1 <= config.planning_above:
                continue
            bearings = [anchors[i].bearing for i in order]
            if any(_gap(a, b) < config.min_bearing_gap_deg for a, b in pairwise(bearings)):
                continue
            weight = [anchors[i].length_m for i in order]
            mean_score = sum(
                anchors[i].score * w for i, w in zip(order, weight, strict=True)
            ) / sum(weight)
            key = frozenset(order)
            for scored, factor in zip(rankings, (scale, 1.0), strict=True):
                rank = mean_score - 40 * abs(estimate * factor / target_s - 1)
                if key not in scored or rank > scored[key][0]:
                    scored[key] = (rank, Plan(order, estimate))

    lists: list[list[Plan]] = []
    for scored in rankings:
        picked: list[Plan] = []
        sets: list[frozenset[int]] = []
        for key, (_, plan) in sorted(scored.items(), key=lambda item: -item[1][0]):
            if any(len(key & other) / len(key | other) > 0.5 for other in sets):
                continue
            picked.append(plan)
            sets.append(key)
            if len(picked) >= config.max_candidates:
                break
        lists.append(picked)

    merged: list[Plan] = []
    seen: set[tuple[int, ...]] = set()
    for pair in zip_longest(*lists):
        for plan in pair:
            if plan is not None and plan.order not in seen:
                seen.add(plan.order)
                merged.append(plan)
    return merged[: config.max_candidates]


# --- putting it together ---------------------------------------------------------


def _metres(a: LatLon, b: LatLon) -> float:
    xy = to_xy(np.array([[a[1], a[0]], [b[1], b[0]]]))
    return float(np.hypot(*(xy[1] - xy[0])))


def _avoid_points(
    edges: Sequence[Edge], leg_start: LatLon, leg_end: LatLon, config: LoopConfig
) -> list[LatLon]:
    """Points on roads already used, to steer the next leg away from them. Roads near the
    leg's own ends are left out, since the leg has to start and finish on them."""
    points: list[LatLon] = []
    last: LatLon | None = None
    for edge in edges:
        if edge.ends is None:
            continue
        (lat1, lon1), (lat2, lon2) = edge.ends
        middle = ((lat1 + lat2) / 2, (lon1 + lon2) / 2)
        if last is not None and _metres(last, middle) < config.avoid_spacing_m:
            continue
        if min(_metres(middle, leg_start), _metres(middle, leg_end)) < config.avoid_clearance_m:
            continue
        points.append(middle)
        last = middle
    if len(points) > config.max_avoid:
        step = len(points) / config.max_avoid
        points = [points[int(i * step)] for i in range(config.max_avoid)]
    return points


def route_loop(
    waypoints: Sequence[LatLon], router: Router, config: LoopConfig
) -> tuple[Route, list[Edge]]:
    """Route the waypoints leg by leg, each leg avoiding the roads the earlier ones used."""
    legs: list[Route] = []
    edges: list[Edge] = []
    for a, b in pairwise(waypoints):
        avoid = _avoid_points(edges, a, b, config)
        try:
            leg = router.route([a, b], avoid)
        except ValhallaError:
            leg = router.route([a, b])  # no way round: use the road again
        legs.append(leg)
        edges.extend(router.edges(leg))
    points: list[LatLon] = []
    for leg in legs:
        points.extend(leg.points[1:] if points else leg.points)
    route = Route(
        distance_km=sum(leg.distance_km for leg in legs),
        duration_s=sum(leg.duration_s for leg in legs),
        leg_shapes=tuple(shape for leg in legs for shape in leg.leg_shapes),
        points=tuple(points),
    )
    return route, edges


def _overlap(a: frozenset[tuple[object, ...]], b: frozenset[tuple[object, ...]]) -> float:
    return len(a & b) / max(1, min(len(a), len(b)))


def generate_loops(
    start: LatLon,
    minutes: float,
    router: Router,
    store: ScoreStore,
    count: int = 3,
    config: LoopConfig | None = None,
) -> LoopResult:
    config = config or LoopConfig()
    if not _inside_data([start], config.edge_margin_deg):
        raise OutsideRegion("that start is too close to the edge of the area we cover")
    result = LoopResult()
    target_valhalla = minutes * config.speed_factor
    outline = router.isochrone(start, max(5.0, config.isochrone_share * target_valhalla))
    anchors = choose_anchors(start, outline, store, config)
    if len(anchors) < 2:
        result.notes.append("There are not enough recommended roads within reach of that start.")
        return result

    points = [start, *(a.point for a in anchors)]
    times = router.matrix(points)
    plans = plan_candidates(times, anchors, target_valhalla * 60, config, config.detour_prior)
    if not plans:
        result.notes.append("No combination of good roads fits that time from that start.")
        return result

    # The matrix knows nothing of the detours that avoiding earlier legs forces, so routed
    # loops run longer than planned, by very different amounts: the loops that pass tend to
    # be the ones with the smallest detours. A plan is therefore skipped only when it cannot
    # fit at any plausible detour, and the range widens if routing shows a wider one.
    target_s = target_valhalla * 60
    ratios = result.detour_ratios
    passing: list[Loop] = []
    for plan in plans:
        low = min([config.detour_low, *ratios])
        high = max([config.detour_high, *ratios])
        if (
            plan.estimate_s * low / target_s - 1 > config.tolerance
            or plan.estimate_s * high / target_s - 1 < -config.tolerance
        ):
            continue
        waypoints = [start, *(anchors[i].point for i in plan.order), start]
        result.candidates_tried += 1
        try:
            route, edges = route_loop(waypoints, router, config)
        except ValhallaError:  # Valhalla could not route this candidate; try the next one
            result.rejected["route"] += 1
            continue
        ratios.append(route.duration_s / plan.estimate_s)
        outcome = evaluate_route(route, edges, waypoints[1:-1], store, minutes, config)
        result.time_ratios.append(route.duration_s / 60 / config.speed_factor / minutes)
        if isinstance(outcome, str):
            result.rejected[outcome] += 1
            if outcome == "time":
                ignoring_time = replace(config, tolerance=1e9)
                other = evaluate_route(route, edges, waypoints[1:-1], store, minutes, ignoring_time)
                result.also_fails["fits" if isinstance(other, Loop) else other] += 1
        else:
            passing.append(outcome)
        if len(passing) >= count * 3:
            break

    # Best score first, with a small penalty for missing the target time so that, between
    # loops of about equal score, the one nearer the time asked for wins.
    def rank(loop: Loop) -> float:
        return loop.score - TIME_PENALTY * abs(loop.duration_min / minutes - 1)

    for loop in sorted(passing, key=lambda lp: -rank(lp)):
        if any(
            _overlap(loop.edge_keys, kept.edge_keys) > config.duplicate_overlap
            for kept in result.loops
        ):
            result.rejected["duplicate"] += 1
            continue
        result.loops.append(loop)
        if len(result.loops) >= count:
            break

    if len(result.loops) < count and result.rejected:
        reasons = ", ".join(
            f"{n} {REJECTION_TEXT.get(key, key)}" for key, n in result.rejected.most_common(3)
        )
        result.notes.append(
            f"Found {len(result.loops)} of {count} loops. Of {result.candidates_tried} "
            f"candidates, {reasons}."
        )
    if result.rejected["time"] and result.time_ratios:
        ratios = sorted(result.time_ratios)
        text = (
            f"Routed loops took {ratios[0]:.2f} to {ratios[-1]:.2f} times the time asked "
            f"(median {median(ratios):.2f}). Routing added a median of "
            f"{median(result.detour_ratios) - 1:.0%} to the matrix's estimate."
        )
        late = result.rejected["time"]
        others = [
            f"{n} {REJECTION_TEXT.get(key, key)}"
            for key, n in result.also_fails.most_common()
            if key != "fits"
        ]
        text += f" Of the {late} that missed on time, "
        if others:
            text += "also " + ", ".join(others)
        fine = result.also_fails["fits"]
        if fine:
            text += (", and " if others else "") + f"{fine} passed every other check"
        text += "."
        result.notes.append(text)
    return result
