"""The reference-road report, using the hand-made map from test_scoring_build."""

import csv
import json
from pathlib import Path

import numpy as np
import pytest
from test_scoring_build import MapWriter, build_map, rolling_heights

from spirited.routing.client import Edge
from spirited.scoring.build import build
from spirited.scoring.evaluate import (
    REFERENCE_PATH,
    ExcludedIndex,
    ReferenceRoad,
    RoadReport,
    format_report,
    headline,
    load_references,
    summarise,
)
from spirited.scoring.geometry import to_lonlat
from spirited.scoring.store import ScoreStore

ROAD = ReferenceRoad("B4009 test", "like", "", (51.4, -1.2), (51.41, -1.19))


@pytest.fixture
def store(tmp_path: Path) -> ScoreStore:
    source = tmp_path / "map.osm"
    build_map(source)
    target = tmp_path / "scores.sqlite"
    build(source, target, rolling_heights)
    return ScoreStore(target)


def test_the_committed_file_is_all_placeholders() -> None:
    roads = load_references(REFERENCE_PATH)
    assert len(roads) == 10
    assert {r.verdict for r in roads} == {"like", "dislike"}
    assert all(r.is_placeholder for r in roads)


def test_a_route_on_the_b_road_gets_its_score(store: ScoreStore) -> None:
    report = summarise(ROAD, [Edge(100, ("B4009",), 1.7), Edge(101, ("B4009",), 1.7)], store)
    assert report.main_label == ("B4009", 1.0)
    assert report.scored_share == 1
    assert report.score > 70
    assert report.components["curvature"] == 1


def test_unscored_stretches_pull_the_score_down(store: ScoreStore) -> None:
    edges = [Edge(100, ("B4009",), 1.0), Edge(102, ("Manor Close",), 1.0)]
    report = summarise(ROAD, edges, store)
    alone = summarise(ROAD, edges[:1], store)
    assert report.score == pytest.approx(alone.score / 2)
    assert report.ineligible_km == {"road_class": 1.0}
    # Confidence and components describe only the scored part.
    assert report.confidence == pytest.approx(alone.confidence)


def test_unknown_ways_are_reported_as_missing(store: ScoreStore) -> None:
    report = summarise(ROAD, [Edge(999, (), 1.0)], store)
    assert report.score == 0
    assert report.ineligible_km == {"missing": 1.0}


def report(name: str, verdict: str, score: float) -> RoadReport:
    return RoadReport(ReferenceRoad(name, verdict, "", (1, 1), (2, 2)), score=score)


def test_headline_counts_liked_roads_above_every_disliked_one() -> None:
    reports = [
        report("a", "like", 80),
        report("b", "like", 50),
        report("c", "dislike", 60),
        report("d", "dislike", 20),
    ]
    assert headline(reports) == (
        "1 of 2 liked roads score above every disliked road; "
        "3 of 4 like/dislike pairs are in the right order."
    )


def test_report_ranks_by_score_and_lists_failures_last() -> None:
    failed = report("broken", "like", 0)
    failed.error = "failed: no route"
    text = format_report([report("low", "dislike", 10), failed, report("high", "like", 90)])
    lines = text.splitlines()
    assert "high" in lines[1]
    assert "low" in lines[2]
    assert "broken" in lines[3] and "no route" in lines[3]


def test_excluded_roads_near_a_route_are_found(tmp_path: Path) -> None:
    m = MapWriter()
    lane = m.line([[0, 20], [500, 20]])  # 20 m from the route below
    far = m.line([[0, 500], [500, 500]])
    m.way(1, lane, {"highway": "unclassified"})
    m.way(2, far, {"highway": "unclassified"})
    m.way(3, m.line([[0, 15], [500, 15]]), {"highway": "footway"})
    source = tmp_path / "region.osm"
    m.write(source)
    excluded_csv = tmp_path / "excluded.csv"
    with excluded_csv.open("w", newline="") as handle:
        rows = csv.writer(handle)
        rows.writerow(["way_id", "highway", "reason", "name", "ref"])
        rows.writerow([1, "unclassified", "unevidenced_unclassified", "", ""])
        rows.writerow([2, "unclassified", "unevidenced_unclassified", "", ""])
        rows.writerow([3, "footway", "highway_class", "", ""])

    index = ExcludedIndex.load(excluded_csv, source)
    route = [(lat, lon) for lon, lat in to_lonlat(np.array([[0.0, 0.0], [500.0, 0.0]]))]
    assert index.near(route) == [(1, "unevidenced_unclassified", "unclassified")]


def test_bad_verdict_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "refs.json"
    entry = {
        "name": "x",
        "verdict": "meh",
        "from": {"lat": 1, "lon": 1},
        "to": {"lat": 1, "lon": 1},
    }
    path.write_text(json.dumps({"roads": [entry]}))
    with pytest.raises(ValueError, match="verdict"):
        load_references(path)


def test_detail_shows_corridors_bends_by_radius_and_climb(store: ScoreStore) -> None:
    import math

    from spirited.routing.client import Route
    from spirited.scoring.evaluate import bends_by_radius, detail_text

    x = np.linspace(0, 3000, 301)
    shape = np.column_stack([x, 40 * np.sin(2 * math.pi * x / 400)])
    points = tuple((lat, lon) for lon, lat in to_lonlat(shape))
    route = Route(3.4, 300, (), points)
    edges = [Edge(100, ("B4009",), 1.7), Edge(101, ("B4009",), 1.7)]
    heights = [(i * 50.0, 100 + 10 * math.sin(i / 10)) for i in range(60)]

    bends = bends_by_radius(points)
    assert bends[100.0] <= bends[150.0] <= bends[200.0] <= bends[300.0]
    assert bends[150.0] > 250  # sustained 100 m radius bends

    text = detail_text(ROAD, route, edges, store, heights)
    assert "B4009 (secondary)" in text
    assert "3.4 km" in text
    assert "https://www.openstreetmap.org/way/100" in text
    assert "<300 m:" in text
    assert "climb per km" in text
