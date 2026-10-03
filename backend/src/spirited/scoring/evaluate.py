"""How the scoring ranks the reference roads: the roads you like and dislike.

    uv run python -m spirited.scoring evaluate

Each reference road is given as two points near its ends. Valhalla routes between
them, the route's OSM ways are looked up in scores.sqlite, and the road gets the
length-weighted score of the corridors it uses. The report also shows any roads within
30 m that the Stage 0 safety filter removed, so a favourite lane that the filter
drops is visible rather than silently missing.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import osmium
import shapely
from osmium.filter import KeyFilter
from osmium.osm import Way

from spirited.region import DATA_DIR
from spirited.routing.client import Edge, Route, ValhallaClient
from spirited.routing.polyline import LatLon
from spirited.scoring import components as c
from spirited.scoring.components import Component
from spirited.scoring.geometry import length_m, resample, to_xy
from spirited.scoring.store import ScoreStore

REFERENCE_PATH = DATA_DIR.parent / "reference_roads.json"
NEARBY_M = 30.0
# Reasons that mean "a road, removed for safety", as opposed to footpaths and the like.
NEARBY_REASONS = frozenset(
    {"access", "unevidenced_unclassified", "byway", "unpaved_surface", "smoothness",
     "tracktype", "ford"}
)  # fmt: skip


@dataclass(frozen=True)
class ReferenceRoad:
    name: str
    verdict: str  # "like" or "dislike"
    why: str
    start: LatLon
    end: LatLon

    @property
    def is_placeholder(self) -> bool:
        return self.name.startswith("PLACEHOLDER") or self.start == (0.0, 0.0)


def load_references(path: Path) -> list[ReferenceRoad]:
    data = json.loads(path.read_text())
    roads = []
    for entry in data["roads"]:
        if entry["verdict"] not in ("like", "dislike"):
            raise ValueError(f"{entry['name']}: verdict must be 'like' or 'dislike'")
        roads.append(
            ReferenceRoad(
                name=entry["name"],
                verdict=entry["verdict"],
                why=entry.get("why", ""),
                start=(float(entry["from"]["lat"]), float(entry["from"]["lon"])),
                end=(float(entry["to"]["lat"]), float(entry["to"]["lon"])),
            )
        )
    return roads


@dataclass
class RoadReport:
    road: ReferenceRoad
    length_km: float = 0.0
    score: float = 0.0
    confidence: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    # Share of the route's length on the label it uses most, e.g. ("B4009", 0.93).
    main_label: tuple[str, float] = ("", 0.0)
    scored_share: float = 0.0
    low_confidence_share: float = 0.0
    ineligible_km: dict[str, float] = field(default_factory=dict)
    nearby_excluded: list[tuple[int, str, str]] = field(default_factory=list)
    detail: str = ""
    error: str = ""


def summarise(road: ReferenceRoad, edges: Sequence[Edge], store: ScoreStore) -> RoadReport:
    """Length-weighted score of the corridors a route uses.

    The score counts the whole route, so unscored stretches (a village, a junction)
    pull it down, as they would on the drive. Confidence and the components count only
    the scored stretches.
    """
    report = RoadReport(road)
    rows = store.corridors_for_ways(e.way_id for e in edges)
    total = sum(e.length_km for e in edges)
    report.length_km = total
    if total == 0:
        report.error = "empty route"
        return report

    by_label: defaultdict[str, float] = defaultdict(float)
    ineligible: defaultdict[str, float] = defaultdict(float)
    scored_km = low_km = score_sum = confidence_sum = 0.0
    component_sums: defaultdict[str, float] = defaultdict(float)
    for edge in edges:
        row = rows.get(edge.way_id)
        km = edge.length_km
        by_label[row["label"] if row else "(not in scores)"] += km
        if row is None:
            ineligible["missing"] += km
            continue
        if row["ineligible"]:
            ineligible[row["ineligible"]] += km
            continue
        scored_km += km
        score_sum += row["score"] * km
        confidence_sum += row["confidence"] * km
        if not row["recommendable"]:
            low_km += km
        for name in Component:
            component_sums[name.value] += (row[f"{name}_score"] or 0.0) * km

    label, km = max(by_label.items(), key=lambda item: item[1])
    report.main_label = (label or "(unnamed)", km / total)
    report.score = score_sum / total
    report.scored_share = scored_km / total
    report.low_confidence_share = low_km / total
    report.ineligible_km = dict(ineligible)
    if scored_km:
        report.confidence = confidence_sum / scored_km
        report.components = {k: v / scored_km for k, v in component_sums.items()}
    return report


# --- roads the safety filter removed --------------------------------------------


class ExcludedIndex:
    """Excluded roads near a line, from excluded-ways.csv and the unfiltered extract."""

    def __init__(self, lines: list[shapely.Geometry], info: list[tuple[int, str, str]]) -> None:
        self._tree = shapely.STRtree(lines)
        self._lines = lines
        self._info = info

    @classmethod
    def load(cls, excluded_csv: Path, unfiltered: Path) -> ExcludedIndex:
        wanted: dict[int, tuple[str, str]] = {}
        with excluded_csv.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if row["reason"] in NEARBY_REASONS:
                    label = row["name"] or row["ref"] or row["highway"]
                    wanted[int(row["way_id"])] = (row["reason"], label)
        lines: list[shapely.Geometry] = []
        info: list[tuple[int, str, str]] = []
        processor = osmium.FileProcessor(str(unfiltered)).with_locations()
        processor.with_filter(KeyFilter("highway"))
        for obj in processor:
            if isinstance(obj, Way) and obj.id in wanted:
                try:
                    points = [(n.location.lon, n.location.lat) for n in obj.nodes]
                except osmium.InvalidLocationError:
                    continue
                if len(points) >= 2:
                    lines.append(shapely.LineString(to_xy(np.array(points))))
                    info.append((obj.id, *wanted[obj.id]))
        return cls(lines, info)

    def near(
        self, route: Sequence[LatLon], distance_m: float = NEARBY_M
    ) -> list[tuple[int, str, str]]:
        if not self._lines or len(route) < 2:
            return []
        line = shapely.LineString(to_xy(np.array([(lon, lat) for lat, lon in route])))
        hits = self._tree.query(line, predicate="dwithin", distance=distance_m)
        return sorted(self._info[i] for i in hits)


# --- the report -------------------------------------------------------------------


def headline(reports: Iterable[RoadReport]) -> str:
    """How many liked roads beat every disliked road, and how many like/dislike pairs
    are in the right order."""
    usable = [r for r in reports if not r.error]
    liked = [r.score for r in usable if r.road.verdict == "like"]
    disliked = [r.score for r in usable if r.road.verdict == "dislike"]
    if not liked or not disliked:
        return "Need at least one liked and one disliked road to compare."
    above_all = sum(score > max(disliked) for score in liked)
    pairs = len(liked) * len(disliked)
    ordered = sum(like > dislike for like in liked for dislike in disliked)
    return (
        f"{above_all} of {len(liked)} liked roads score above every disliked road; "
        f"{ordered} of {pairs} like/dislike pairs are in the right order."
    )


def recommendation_line(reports: Iterable[RoadReport]) -> str:
    """How many liked and disliked roads the app would recommend: those with at least
    half of the route in recommendable corridors. Unscored stretches (a dual carriageway)
    count against a road, as they would on the drive, and a disliked road that is not
    recommended is handled correctly whatever its score."""
    usable = [r for r in reports if not r.error]
    out = []
    for verdict in ("like", "dislike"):
        roads = [r for r in usable if r.road.verdict == verdict]
        kept = sum(r.scored_share - r.low_confidence_share >= 0.5 for r in roads)
        out.append(f"{kept} of {len(roads)} {verdict}d roads")
    return f"The app would recommend {out[0]} and {out[1]}."


_SHORT = {
    Component.CURVATURE: "curve",
    Component.ROAD_CLASS: "class",
    Component.SPEED: "speed",
    Component.JUNCTIONS: "junct",
    Component.SETTLEMENT: "settl",
    Component.ELEVATION: "elev",
}


def format_report(reports: list[RoadReport]) -> str:
    ranked = sorted(reports, key=lambda r: (bool(r.error), -r.score))
    parts = "  ".join(f"{_SHORT[name]:>5}" for name in Component)
    lines = [
        f"{'#':>2}  {'verdict':7}  {'road':28}  {'km':>5}  {'score':>5}  {'conf':>4}  {parts}"
        f"  {'scored':>6}  {'low-conf':>8}  main road",
    ]
    for rank, r in enumerate(ranked, 1):
        if r.error:
            lines.append(f"{'-':>2}  {r.road.verdict:7}  {r.road.name[:28]:28}  {r.error}")
            continue
        values = "  ".join(f"{r.components.get(name.value, 0.0):5.2f}" for name in Component)
        label, share = r.main_label
        lines.append(
            f"{rank:>2}  {r.road.verdict:7}  {r.road.name[:28]:28}  {r.length_km:5.1f}"
            f"  {r.score:5.1f}  {r.confidence:4.2f}  {values}  {r.scored_share:6.0%}"
            f"  {r.low_confidence_share:8.0%}  {label} ({share:.0%})"
        )
    lines += ["", headline(reports), recommendation_line(reports)]

    notes = []
    for r in ranked:
        if r.ineligible_km:
            why = ", ".join(f"{k} {v:.1f} km" for k, v in sorted(r.ineligible_km.items()))
            notes.append(f"{r.road.name}: unscored stretches: {why}")
        for way_id, reason, label in r.nearby_excluded:
            notes.append(
                f"{r.road.name}: removed by the filter within {NEARBY_M:.0f} m: "
                f"way {way_id} ({label}, {reason})"
            )
        if not r.error and r.main_label[1] < 0.6:
            notes.append(
                f"{r.road.name}: the route spends only {r.main_label[1]:.0%} on its main road; "
                "check the two points are on the road you meant"
            )
    if notes:
        lines += ["", "Notes:", *(f"- {note}" for note in notes)]
    return "\n".join(lines)


# --- detail: what lies behind a road's score --------------------------------------

DETAIL_RADII_M = (100.0, 150.0, 200.0, 300.0)


def bends_by_radius(
    points: Sequence[LatLon], radii: Sequence[float] = DETAIL_RADII_M
) -> dict[float, float]:
    """Metres per km inside sustained bends for several bend radii, from a route's shape.

    The score counts only bends under c.BEND_RADIUS_M. Showing wider radii tells us
    whether a road is flowing rather than tight, which that single threshold cannot.
    """
    xy = to_xy(np.array([(lon, lat) for lat, lon in points]))
    km = length_m(xy) / 1000
    resampled = resample(xy, c.STEP_M)
    return {r: (c.bend_metres(resampled, r) / km if km else 0.0) for r in radii}


def detail_text(
    road: ReferenceRoad,
    route: Route,
    edges: Sequence[Edge],
    store: ScoreStore,
    heights: Sequence[tuple[float, float]],
) -> str:
    """The corridors a route uses, its bends at several radii, and its climb."""
    rows = store.corridors_for_ways(e.way_id for e in edges)
    km_on: defaultdict[int, float] = defaultdict(float)
    order: list[int] = []
    for edge in edges:
        row = rows.get(edge.way_id)
        corridor_id = row["id"] if row else -edge.way_id
        if corridor_id not in km_on:
            order.append(corridor_id)
        km_on[corridor_id] += edge.length_km
    by_id = {row["id"]: row for row in rows.values()}

    lines = [f"{road.name} ({road.verdict}): {road.why}".rstrip(": ")]
    lines.append("  corridors on the route (km on route, then the whole corridor's figures):")
    for corridor_id in order:
        row = by_id.get(corridor_id)
        km = km_on[corridor_id]
        if row is None:
            lines.append(f"    {km:4.1f} km  not in scores (way {-corridor_id})")
            continue
        status = row["ineligible"] or ("recommended" if row["recommendable"] else "low confidence")
        lines.append(
            f"    {km:4.1f} km  {row['label'] or '(unnamed)'} ({row['highway']}), "
            f"score {row['score']:.0f}, conf {row['confidence'] or 0:.2f}, {status}, "
            f"narrow {row['narrow_share'] or 0:.1f}, surface x{row['surface_factor'] or 0:.2f}, "
            f"{row['mph']:.0f} mph ({row['speed_source']}), "
            f"https://www.openstreetmap.org/way/{corridor_id}"
        )
    bends = bends_by_radius(route.points)
    lines.append(
        "  bend metres per km by radius: "
        + ", ".join(f"<{r:.0f} m: {v:.0f}" for r, v in bends.items())
        + f"   (the score uses <{c.BEND_RADIUS_M:.0f} m, full marks at "
        f"{c.FULL_CURVATURE_M_PER_KM:.0f})"
    )
    if len(heights) >= 3 and route.distance_km:
        values = [h for _, h in heights]
        smooth = c.climb_m(c.smooth_heights(values, c.HEIGHT_STEP_M)) / route.distance_km
        raw = c.climb_m(values, 0.0) / route.distance_km
        lines.append(
            f"  climb per km: {smooth:.1f} m smoothed (scored), {raw:.1f} m raw; "
            f"{len(values)} height samples, full marks at {c.FULL_CLIMB_M_PER_KM:.0f}"
        )
    return "\n".join(lines)


def evaluate(
    roads: list[ReferenceRoad],
    client: ValhallaClient,
    store: ScoreStore,
    excluded: ExcludedIndex | None,
    detail: bool = False,
) -> list[RoadReport]:
    reports = []
    for road in roads:
        try:
            route = client.route([road.start, road.end])
            edges = client.edges(route)
            report = summarise(road, edges, store)
            if excluded is not None:
                report.nearby_excluded = excluded.near(route.points)
            if detail:
                heights = client.elevation(route, every_m=int(c.HEIGHT_STEP_M))
                report.detail = detail_text(road, route, edges, store, heights)
        except Exception as error:  # report the road and carry on with the rest
            report = RoadReport(road, error=f"failed: {error}")
        reports.append(report)
    return reports
