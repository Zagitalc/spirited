"""The whole build on a small hand-made map: OSM file in, scores.sqlite out."""

import json
import math
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from spirited.scoring.build import build, summary
from spirited.scoring.geometry import Coords, to_lonlat


class MapWriter:
    """Writes OSM XML from shapes given in metres on the scoring plane."""

    def __init__(self) -> None:
        self.nodes: list[str] = []
        self.ways: list[tuple[int, str]] = []
        self._next_node = 1

    def node(self, x: float, y: float, tags: dict[str, str] | None = None) -> int:
        node_id = self._next_node
        self._next_node += 1
        lon, lat = to_lonlat(np.array([[x, y]]))[0]
        body = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in (tags or {}).items())
        self.nodes.append(
            f'<node id="{node_id}" version="1" lat="{lat:.7f}" lon="{lon:.7f}">{body}</node>'
        )
        return node_id

    def line(self, xy: Sequence[Sequence[float]] | np.ndarray) -> list[int]:
        return [self.node(x, y) for x, y in xy]

    def way(self, way_id: int, nodes: Sequence[int], tags: dict[str, str]) -> None:
        refs = "".join(f'<nd ref="{n}"/>' for n in nodes)
        body = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
        self.ways.append((way_id, f'<way id="{way_id}" version="1">{refs}{body}</way>'))

    def write(self, path: Path) -> None:
        path.write_text(
            "<?xml version='1.0' encoding='UTF-8'?>\n<osm version=\"0.6\">\n"
            + "\n".join(self.nodes + [text for _, text in sorted(self.ways)])
            + "\n</osm>\n"
        )


def build_map(path: Path) -> dict[str, int]:
    m = MapWriter()
    # A twisty B road, 3 km of 100 m radius bends, drawn as two ways.
    x = np.linspace(0, 3000, 301)
    b_road = m.line(np.column_stack([x, 40 * np.sin(2 * math.pi * x / 400)]))
    m.way(100, b_road[:151], {"highway": "secondary", "ref": "B4009"})
    m.way(101, b_road[150:], {"highway": "secondary", "ref": "B4009"})
    # A housing estate road leaving the B road half way along the first way.
    estate = [b_road[75], *m.line([[750, -200], [750, -400]])]
    m.way(102, estate, {"highway": "residential", "name": "Manor Close"})

    # A straight 40 mph A road, 2 km, with traffic lights in the middle and the
    # first quarter running through a housing estate.
    a_road = m.line([[d, 2000] for d in range(0, 2001, 100)])
    m.nodes[a_road[10] - 1] = m.nodes[a_road[10] - 1].replace(
        "></node>", '><tag k="highway" v="traffic_signals"/></node>'
    )
    m.way(200, a_road, {"highway": "primary", "ref": "A4", "maxspeed": "40 mph"})
    estate_edge = m.line([[-100, 1800], [500, 1800], [500, 2200], [-100, 2200]])
    m.way(900, [*estate_edge, estate_edge[0]], {"landuse": "residential"})

    # A village street with no speed limit tag, drawn without a landuse polygon.
    m.node(5000, 0, {"place": "village", "name": "Little Hampden"})
    village = m.line([[4800, 0], [5000, 0], [5200, 0]])
    m.way(300, village, {"highway": "tertiary", "name": "Church Lane"})

    # The same twisty shape again, as a single-track lane with a passing place.
    lane = m.line(np.column_stack([x, 6000 + 40 * np.sin(2 * math.pi * x / 400)]))
    m.nodes[lane[150] - 1] = m.nodes[lane[150] - 1].replace(
        "></node>", '><tag k="highway" v="passing_place"/></node>'
    )
    m.way(400, lane, {"highway": "unclassified", "name": "Mill Lane"})

    m.write(path)
    return {"b_road": 100, "estate": 102, "a_road": 200, "village": 300}


def rolling_heights(samples: Sequence[Coords]) -> list[np.ndarray | None]:
    """20 m hills every 2 km, so every road climbs a little."""
    out: list[np.ndarray | None] = []
    for sample in samples:
        distance = np.arange(len(sample)) * 50.0
        out.append(100 + 20 * np.sin(distance / 2000 * 2 * math.pi))
    return out


@pytest.fixture
def scores(tmp_path: Path) -> sqlite3.Connection:
    source = tmp_path / "map.osm"
    build_map(source)
    target = tmp_path / "scores.sqlite"
    result = build(source, target, rolling_heights)
    assert summary(result)["corridors"] == 5
    db = sqlite3.connect(target)
    db.row_factory = sqlite3.Row
    return db


def corridor(db: sqlite3.Connection, way_id: int) -> sqlite3.Row:
    return db.execute(
        "SELECT c.* FROM corridors c JOIN corridor_ways w ON w.corridor_id = c.id "
        "WHERE w.way_id = ?",
        (way_id,),
    ).fetchone()


def test_the_twisty_b_road_is_one_corridor_and_scores_well(scores: sqlite3.Connection) -> None:
    row = corridor(scores, 101)
    assert row["id"] == 100
    assert row["way_count"] == 2
    assert row["length_m"] == pytest.approx(3400, rel=0.1)  # longer than 3 km: it bends
    assert row["ineligible"] is None
    assert row["curvature_score"] == 1
    assert row["speed_source"] == "assumed"
    assert row["junctions_per_km"] == pytest.approx(1 / 3.4, rel=0.1)  # the estate road
    assert row["climb_m_per_km"] > 0
    assert row["elevation_conf"] == pytest.approx(0.6)
    assert row["score"] > 70


def test_the_straight_a_road_scores_lower(scores: sqlite3.Connection) -> None:
    a_road, b_road = corridor(scores, 200), corridor(scores, 100)
    assert a_road["mph"] == 40
    assert a_road["speed_source"] == "tagged"
    assert a_road["curvature_score"] == 0
    assert a_road["junctions_per_km"] == pytest.approx(1.0)  # traffic lights count double
    assert a_road["settlement_share"] == pytest.approx(0.25, abs=0.02)
    assert a_road["score"] < b_road["score"] - 30


def test_residential_and_village_roads_never_score(scores: sqlite3.Connection) -> None:
    estate = corridor(scores, 102)
    assert (estate["ineligible"], estate["score"], estate["recommendable"]) == ("road_class", 0, 0)
    village = corridor(scores, 300)
    assert village["ineligible"] == "speed_limit"
    assert village["speed_source"] == "settlement"
    assert village["mph"] == 30


def test_confidence_and_recommendations(scores: sqlite3.Connection) -> None:
    b_road = corridor(scores, 100)
    # Speed assumed and surface presumed both lower confidence, but not below the bar.
    assert 0.6 <= b_road["confidence"] < 0.9
    assert b_road["recommendable"] == 1
    a_road = corridor(scores, 200)
    # Tagged speed: more confident than the B road, whose limit is assumed.
    assert a_road["confidence"] > b_road["confidence"]


def test_build_metadata(scores: sqlite3.Connection) -> None:
    meta = {k: json.loads(v) for k, v in scores.execute("SELECT key, value FROM meta")}
    assert meta["heights"] is True
    assert sum(meta["weights"].values()) == pytest.approx(1)


def test_without_heights_elevation_has_no_confidence(tmp_path: Path) -> None:
    source = tmp_path / "map.osm"
    build_map(source)
    target = tmp_path / "scores.sqlite"
    build(source, target, heights=None)
    db = sqlite3.connect(target)
    query = "SELECT elevation_score, elevation_conf FROM corridors WHERE id = 100"
    row = db.execute(query).fetchone()
    assert row == (0, 0)


def test_a_single_track_lane_scores_lower_than_the_same_bends_on_a_b_road(
    scores: sqlite3.Connection,
) -> None:
    lane, b_road = corridor(scores, 400), corridor(scores, 100)
    assert lane["narrow_share"] == 1
    assert b_road["narrow_share"] == 0
    assert lane["curvature_score"] == b_road["curvature_score"] == 1
    assert lane["score"] < b_road["score"] * 0.6


def test_an_unclassified_road_without_a_surface_tag_is_never_recommended(
    scores: sqlite3.Connection,
) -> None:
    lane = corridor(scores, 400)
    assert lane["surface_factor"] == pytest.approx(0.55)
    assert lane["confidence"] < 0.6
    assert lane["recommendable"] == 0
