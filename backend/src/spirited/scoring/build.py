"""Score every road in the filtered extract and write the results to SQLite.

    uv run python -m spirited.scoring build

Reads `region-filtered.osm.pbf` twice: once for roads, junction nodes and village
names, once for built-up land use. Heights come from Valhalla, which must be running
unless `--no-heights` is given (elevation then scores 0 with no confidence).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import osmium
import shapely
from numpy.typing import NDArray
from osmium.filter import KeyFilter
from osmium.geom import WKBFactory
from osmium.osm import Area, Node, Way

from spirited.region import DATA_DIR
from spirited.roadfilter import PAVED_SURFACES, ROUTABLE_CLASSES
from spirited.routing.client import ValhallaClient
from spirited.scoring import components as c
from spirited.scoring.components import Component, Ineligible, Part
from spirited.scoring.corridors import Corridor, WaySegment, build_corridors
from spirited.scoring.geometry import (
    Coords,
    length_m,
    mean_node_spacing_m,
    resample,
    to_lonlat,
    to_xy,
)
from spirited.scoring.speed import SpeedLimit, SpeedSource, speed_limit

SCORES_PATH = DATA_DIR.parent / "scores.sqlite"

SETTLEMENT_LANDUSE = frozenset({"residential", "retail", "commercial"})
# Radius around a place node treated as built up, for villages drawn without a
# landuse polygon. Towns and cities almost always have landuse, so theirs is a backstop.
PLACE_RADIUS_M = {"city": 3000.0, "town": 1500.0, "village": 400.0, "hamlet": 150.0}
JUNCTION_NODES = frozenset({"traffic_signals", "mini_roundabout"})
# Passing places only exist on single-track roads.
SINGLE_TRACK_NODES = frozenset({"passing_place"})

# Confidence of each component that does not depend on the road's own tags.
ROAD_CLASS_CONFIDENCE = 1.0
JUNCTION_CONFIDENCE = 0.9
SETTLEMENT_CONFIDENCE = {"landuse": 0.9, "place_only": 0.6}
ELEVATION_CONFIDENCE = 0.6
# A road kept by the filter only because its class is presumed paved.
PRESUMED_SURFACE_FACTOR = 0.9
# An unclassified road with no surface tag is suspect (the project's safety rule).
# This factor alone takes it below MIN_CONFIDENCE, so such a road can be routed over
# but never recommended for itself.
UNTAGGED_MINOR_SURFACE_FACTOR = 0.55

HeightSource = Callable[[Sequence[Coords]], list[NDArray[np.float64] | None]]
"""Takes (lon, lat) sample points per corridor and returns heights in metres per corridor."""


@dataclass
class RawWay:
    id: int
    tags: dict[str, str]
    node_ids: tuple[int, ...]
    lonlat: Coords


@dataclass
class Region:
    ways: list[RawWay] = field(default_factory=list)
    node_degree: Counter[int] = field(default_factory=Counter)
    junction_nodes: set[int] = field(default_factory=set)
    roundabout_nodes: set[int] = field(default_factory=set)
    passing_places: set[int] = field(default_factory=set)
    landuse: shapely.Geometry | None = None
    places: shapely.Geometry | None = None


_WAY_TAGS = (
    "highway",
    "ref",
    "name",
    "maxspeed",
    "maxspeed:type",
    "source:maxspeed",
    "lit",
    "junction",
    "dual_carriageway",
    "surface",
    "lanes",
    "width",
    "est_width",
    "oneway",
)


def read_region(path: Path) -> Region:
    region = Region()
    place_circles: list[shapely.Geometry] = []
    roads = osmium.FileProcessor(str(path)).with_locations()
    roads.with_filter(KeyFilter("highway", "place"))
    for obj in roads:
        if isinstance(obj, Node):
            if obj.tags.get("highway", "") in JUNCTION_NODES:
                region.junction_nodes.add(obj.id)
            if obj.tags.get("highway", "") in SINGLE_TRACK_NODES:
                region.passing_places.add(obj.id)
            radius = PLACE_RADIUS_M.get(obj.tags.get("place") or "")
            if radius and obj.location.valid():
                centre = to_xy(np.array([[obj.location.lon, obj.location.lat]]))[0]
                place_circles.append(shapely.Point(centre).buffer(radius, quad_segs=8))
        elif isinstance(obj, Way):
            highway = obj.tags.get("highway")
            if highway not in ROUTABLE_CLASSES:
                continue
            node_ids = tuple(n.ref for n in obj.nodes)
            if any(not n.location.valid() for n in obj.nodes):
                continue
            lonlat = np.array([[n.location.lon, n.location.lat] for n in obj.nodes])
            tags = {k: obj.tags[k] for k in _WAY_TAGS if k in obj.tags}
            region.ways.append(RawWay(obj.id, tags, node_ids, lonlat))
            for node in set(node_ids):
                region.node_degree[node] += 1
            if tags.get("junction") in ("roundabout", "circular"):
                region.roundabout_nodes.update(node_ids)

    polygons: list[shapely.Geometry] = []
    wkb = WKBFactory()
    areas = osmium.FileProcessor(str(path)).with_areas(KeyFilter("landuse"))
    areas.with_filter(KeyFilter("landuse"))
    for obj in areas:
        if isinstance(obj, Area) and obj.tags.get("landuse") in SETTLEMENT_LANDUSE:
            try:
                geometry = shapely.from_wkb(wkb.create_multipolygon(obj))
            except RuntimeError:
                continue  # broken multipolygon in OSM; skip it
            polygons.append(shapely.transform(geometry, to_xy))

    region.landuse = shapely.union_all(polygons) if polygons else None
    region.places = shapely.union_all(place_circles) if place_circles else None
    for geometry in (region.landuse, region.places):
        if geometry is not None:
            shapely.prepare(geometry)
    return region


@dataclass(frozen=True)
class Settlement:
    share: float
    # True when some of the road counts as built up only because of a place node.
    place_only: bool


def settlement(xy: Coords, region: Region) -> Settlement:
    points = resample(xy, c.STEP_M)
    in_landuse = _inside(region.landuse, points)
    in_place = _inside(region.places, points)
    inside = in_landuse | in_place
    return Settlement(float(inside.mean()), bool((in_place & ~in_landuse).any()))


def _inside(geometry: shapely.Geometry | None, xy: Coords) -> NDArray[np.bool_]:
    if geometry is None or len(xy) == 0:
        return np.zeros(len(xy), dtype=bool)
    return np.asarray(shapely.contains_xy(geometry, xy[:, 0], xy[:, 1]), dtype=bool)


@dataclass
class WayFacts:
    way: RawWay
    xy: Coords
    length_m: float
    settlement: Settlement
    speed: SpeedLimit
    ineligible: Ineligible | None


def way_facts(way: RawWay, region: Region) -> WayFacts:
    xy = to_xy(way.lonlat)
    place = settlement(xy, region)
    speed = speed_limit(way.tags, in_settlement=place.share > 0.5)
    ineligible = c.ineligible_reason(way.tags["highway"], speed.mph)
    if way.tags.get("junction") in ("roundabout", "circular"):
        ineligible = Ineligible.ROUNDABOUT
    return WayFacts(way, xy, length_m(xy), place, speed, ineligible)


def _segment(facts: WayFacts) -> WaySegment:
    tags = facts.way.tags
    label = tags.get("ref") or tags.get("name") or ""
    reason = facts.ineligible.value if facts.ineligible else ""
    return WaySegment(
        way_id=facts.way.id,
        node_ids=facts.way.node_ids,
        lonlat=facts.way.lonlat,
        key=(label, tags["highway"], reason),
        labelled=bool(label),
        roundabout=facts.ineligible is Ineligible.ROUNDABOUT,
    )


@dataclass
class CorridorScore:
    corridor: Corridor
    highway: str
    label: str
    length_m: float
    ineligible: Ineligible | None
    mph: float
    speed_source: SpeedSource
    parts: dict[Component, Part] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    surface_factor: float = 1.0
    score: float = 0.0
    confidence: float = 0.0

    @property
    def too_short(self) -> bool:
        return self.length_m < c.MIN_CORRIDOR_M

    @property
    def recommendable(self) -> bool:
        return (
            self.ineligible is None and not self.too_short and self.confidence >= c.MIN_CONFIDENCE
        )


def _weighted(values: Iterable[tuple[float, float]]) -> float:
    pairs = list(values)
    total = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / total if total else 0.0


def junctions_per_km(
    corridor: Corridor,
    way_nodes: Iterable[tuple[int, ...]],
    region: Region,
    corridor_length_m: float,
) -> float:
    """Side roads, signals and roundabouts met along the corridor, per km.

    Only nodes inside the corridor count: its ends are junctions shared with the next
    corridor. Signals, mini-roundabouts and roundabouts count double.
    """
    own: Counter[int] = Counter()
    for nodes in way_nodes:
        for node in set(nodes):
            own[node] += 1
    count = 0.0
    for node in corridor.node_ids[1:-1]:
        if node in region.junction_nodes or node in region.roundabout_nodes:
            count += 2
        elif region.node_degree[node] > own[node]:
            count += 1
    return count / (corridor_length_m / 1000) if corridor_length_m else 0.0


def score_corridors(
    region: Region, heights: HeightSource | None
) -> tuple[list[CorridorScore], dict[int, int]]:
    facts = {way.id: way_facts(way, region) for way in region.ways}
    corridors = build_corridors([_segment(f) for f in facts.values()], region.node_degree)
    scores: list[CorridorScore] = []
    for corridor in corridors:
        members = [facts[way_id] for way_id in corridor.way_ids]
        length = sum(f.length_m for f in members)
        worst = min(members, key=lambda f: f.speed.confidence)
        scores.append(
            CorridorScore(
                corridor=corridor,
                highway=members[0].way.tags["highway"],
                label=corridor.key[0],
                length_m=length,
                ineligible=members[0].ineligible,
                mph=_weighted((f.speed.mph, f.length_m) for f in members),
                speed_source=worst.speed.source,
            )
        )

    eligible = [s for s in scores if s.ineligible is None]
    samples = [to_lonlat(resample(to_xy(s.corridor.lonlat), c.HEIGHT_STEP_M)) for s in eligible]
    profile = heights(samples) if heights else [None] * len(eligible)
    for item, height in zip(eligible, profile, strict=True):
        _score(item, [facts[w] for w in item.corridor.way_ids], region, height)

    way_to_corridor = {way: s.corridor.id for s in scores for way in s.corridor.way_ids}
    return scores, way_to_corridor


def _score(
    item: CorridorScore,
    members: list[WayFacts],
    region: Region,
    height: NDArray[np.float64] | None,
) -> None:
    xy = to_xy(item.corridor.lonlat)
    km = item.length_m / 1000

    bends = c.bends_per_km(xy)
    spacing = mean_node_spacing_m(xy)
    per_km = junctions_per_km(
        item.corridor, [f.way.node_ids for f in members], region, item.length_m
    )
    place = settlement(xy, region)
    speed_conf = _weighted((f.speed.confidence, f.length_m) for f in members)

    climb = 0.0
    if height is not None and len(height) >= 2:
        climb = c.climb_m(c.smooth_heights(height)) / km if km else 0.0
        elevation = Part(c.elevation_score(climb), ELEVATION_CONFIDENCE)
    else:
        elevation = Part(0.0, 0.0)

    item.parts = {
        Component.CURVATURE: Part(c.curvature_score(bends), c.curvature_confidence(spacing)),
        Component.ROAD_CLASS: Part(c.road_class_score(item.highway), ROAD_CLASS_CONFIDENCE),
        Component.SPEED: Part(c.speed_score(item.mph), speed_conf),
        Component.JUNCTIONS: Part(c.junction_score(per_km), JUNCTION_CONFIDENCE),
        Component.SETTLEMENT: Part(
            c.settlement_score(place.share),
            SETTLEMENT_CONFIDENCE["place_only" if place.place_only else "landuse"],
        ),
        Component.ELEVATION: elevation,
    }
    item.metrics = {
        "bends_m_per_km": bends,
        "node_spacing_m": spacing,
        "junctions_per_km": per_km,
        "settlement_share": place.share,
        "climb_m_per_km": climb,
    }
    item.surface_factor = _weighted((_surface_factor(f.way.tags), f.length_m) for f in members)
    if any(node in region.passing_places for node in item.corridor.node_ids):
        narrow = 1.0
    else:
        narrow = _weighted((c.narrowness(f.way.tags), f.length_m) for f in members)
    item.metrics["narrow_share"] = narrow
    score, confidence = c.combine(item.parts)
    item.score = score * c.narrow_factor(narrow)
    item.confidence = confidence * item.surface_factor


def _surface_factor(tags: dict[str, str]) -> float:
    if tags.get("surface") in PAVED_SURFACES:
        return 1.0
    if tags.get("highway") == "unclassified":
        return UNTAGGED_MINOR_SURFACE_FACTOR
    return PRESUMED_SURFACE_FACTOR


# --- heights from Valhalla ----------------------------------------------------


def valhalla_heights(client: ValhallaClient, batch: int = 10_000) -> HeightSource:
    """A HeightSource that asks Valhalla's /height in batches of `batch` points."""

    def lookup(samples: Sequence[Coords]) -> list[NDArray[np.float64] | None]:
        flat = np.concatenate(samples) if samples else np.zeros((0, 2))
        values: list[float | None] = []
        for start in range(0, len(flat), batch):
            chunk = flat[start : start + batch]
            values.extend(client.heights([(float(lat), float(lon)) for lon, lat in chunk]))
        result: list[NDArray[np.float64] | None] = []
        offset = 0
        for sample in samples:
            part = values[offset : offset + len(sample)]
            offset += len(sample)
            known = [v for v in part if v is not None]
            result.append(np.array(known) if len(known) == len(part) else None)
        return result

    return lookup


# --- writing ------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE corridors (
    id INTEGER PRIMARY KEY,
    highway TEXT NOT NULL,
    label TEXT NOT NULL,
    length_m REAL NOT NULL,
    way_count INTEGER NOT NULL,
    ineligible TEXT,
    too_short INTEGER NOT NULL,
    recommendable INTEGER NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    mph REAL NOT NULL,
    speed_source TEXT NOT NULL,
    bends_m_per_km REAL,
    node_spacing_m REAL,
    junctions_per_km REAL,
    settlement_share REAL,
    climb_m_per_km REAL,
    narrow_share REAL,
    surface_factor REAL,
    {parts}
);
CREATE TABLE corridor_ways (
    way_id INTEGER PRIMARY KEY,
    corridor_id INTEGER NOT NULL REFERENCES corridors(id)
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def write_scores(
    path: Path,
    scores: list[CorridorScore],
    way_to_corridor: dict[int, int],
    meta: dict[str, object],
) -> None:
    part_columns = ",\n    ".join(f"{name}_score REAL, {name}_conf REAL" for name in Component)
    tmp = path.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    with sqlite3.connect(tmp) as db:
        db.executescript(_SCHEMA.format(parts=part_columns))
        columns = [
            "id", "highway", "label", "length_m", "way_count", "ineligible", "too_short",
            "recommendable", "score", "confidence", "mph", "speed_source",
            "bends_m_per_km", "node_spacing_m", "junctions_per_km", "settlement_share",
            "climb_m_per_km", "narrow_share", "surface_factor",
        ]  # fmt: skip
        for name in Component:
            columns += [f"{name}_score", f"{name}_conf"]
        rows = []
        for s in scores:
            row: list[object] = [
                s.corridor.id, s.highway, s.label, s.length_m, len(s.corridor.way_ids),
                s.ineligible.value if s.ineligible else None, int(s.too_short),
                int(s.recommendable), s.score, s.confidence, s.mph, s.speed_source.value,
            ]  # fmt: skip
            row += [s.metrics.get(key) for key in (
                "bends_m_per_km", "node_spacing_m", "junctions_per_km", "settlement_share",
                "climb_m_per_km", "narrow_share",
            )]  # fmt: skip
            row.append(s.surface_factor if s.parts else None)
            for name in Component:
                part = s.parts.get(name)
                row += [part.value if part else None, part.confidence if part else None]
            rows.append(row)
        marks = ", ".join("?" for _ in columns)
        db.executemany(f"INSERT INTO corridors ({', '.join(columns)}) VALUES ({marks})", rows)
        db.executemany("INSERT INTO corridor_ways VALUES (?, ?)", way_to_corridor.items())
        db.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [(key, json.dumps(value)) for key, value in meta.items()],
        )
    tmp.replace(path)


def build(source: Path, target: Path, heights: HeightSource | None) -> list[CorridorScore]:
    started = time.monotonic()
    region = read_region(source)
    scores, way_to_corridor = score_corridors(region, heights)
    meta = {
        "source": source.name,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "weights": {name.value: weight for name, weight in c.WEIGHTS.items()},
        "min_confidence": c.MIN_CONFIDENCE,
        "heights": heights is not None,
        "seconds": round(time.monotonic() - started, 1),
    }
    write_scores(target, scores, way_to_corridor, meta)
    return scores


def summary(scores: list[CorridorScore]) -> dict[str, object]:
    """Counts for the build log: how much road is scored, and why the rest is not."""
    km: defaultdict[str, float] = defaultdict(float)
    for s in scores:
        if s.ineligible:
            km[f"ineligible:{s.ineligible.value}"] += s.length_m / 1000
        elif s.too_short:
            km["scored:too_short"] += s.length_m / 1000
        elif s.recommendable:
            km["scored:recommendable"] += s.length_m / 1000
        else:
            km["scored:low_confidence"] += s.length_m / 1000
    sources: defaultdict[str, float] = defaultdict(float)
    for s in scores:
        sources[s.speed_source.value] += s.length_m / 1000
    return {
        "corridors": len(scores),
        "km_by_outcome": _rounded(km),
        "km_by_speed_source": _rounded(sources),
    }


def _rounded(km: dict[str, float]) -> dict[str, int]:
    return {key: round(value) for key, value in sorted(km.items(), key=lambda kv: -kv[1])}
