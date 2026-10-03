"""Loop generation against a made-up score database and a straight-line router."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from loop_support import ANCHOR_KM, START, FakeRouter, make_store, ring_point

from spirited.loops.config import LoopConfig
from spirited.loops.generate import (
    Anchor,
    Group,
    Loop,
    OutsideRegion,
    choose_anchors,
    classify,
    evaluate_route,
    generate_loops,
    plan_candidates,
)
from spirited.routing.client import Edge, Route
from spirited.scoring.store import ScoreStore

CONFIG = LoopConfig()


@pytest.fixture
def mids(tmp_path: Path):
    return make_store(tmp_path / "scores.sqlite")


@pytest.fixture
def store(tmp_path: Path, mids) -> Iterator[ScoreStore]:
    with ScoreStore(tmp_path / "scores.sqlite") as store:
        yield store


def row(store: ScoreStore, way_id: int) -> sqlite3.Row:
    return store.corridors_for_ways([way_id])[way_id]


def test_corridors_fall_into_three_groups(store: ScoreStore) -> None:
    assert classify(row(store, 10)) is Group.RECOMMENDED
    assert classify(row(store, 200)) is Group.BUILT_UP  # residential
    assert classify(row(store, 240)) is Group.BUILT_UP  # village at 30 mph
    assert classify(row(store, 210)) is Group.NOT_RECOMMENDED  # low confidence
    assert classify(row(store, 220)) is Group.NOT_RECOMMENDED  # dual carriageway
    assert classify(None) is Group.NOT_RECOMMENDED


# --- evaluating one route ---------------------------------------------------------


def make_route(km: float, valhalla_minutes: float) -> Route:
    """A route that runs from the start to a point `km` east and back."""
    far = (START[0], START[1] + km / 2 / 69.5)
    return Route(
        distance_km=km,
        duration_s=valhalla_minutes * 60,
        leg_shapes=(),
        points=(START, far, START),
    )


def edges_of(*parts: tuple[int, float]) -> list[Edge]:
    return [Edge(way, ("x",), km) for way, km in parts]


def check(store: ScoreStore, edges: list[Edge], minutes: float = 60.0) -> Loop | str:
    total = sum(e.length_km for e in edges)
    # Valhalla minutes that come out as `minutes` once the speed factor is applied.
    route = make_route(total, minutes * CONFIG.speed_factor)
    return evaluate_route(route, edges, [START], store, minutes, CONFIG)


def test_a_loop_on_recommended_roads_is_accepted_with_its_score(store: ScoreStore) -> None:
    loop = check(store, edges_of((10, 10), (20, 10), (30, 10)))
    assert isinstance(loop, Loop)
    assert loop.score == pytest.approx(70)
    assert loop.shares[Group.RECOMMENDED] == 1
    assert loop.duration_min == pytest.approx(60)
    assert [s.road for s in loop.segments] == ["B4001", "B4002", "B4003"]
    assert loop.warnings == ()


def test_unrecommended_and_built_up_road_count_as_zero_in_the_score(store: ScoreStore) -> None:
    loop = check(store, edges_of((10, 8), (200, 1), (210, 1)))
    assert isinstance(loop, Loop)
    assert loop.score == pytest.approx(70 * 0.8)
    assert loop.shares[Group.BUILT_UP] == pytest.approx(0.1)
    assert loop.shares[Group.NOT_RECOMMENDED] == pytest.approx(0.1)
    assert loop.warnings == ("10% of this loop is on roads we cannot vouch for",)


@pytest.mark.parametrize(
    ("parts", "reason"),
    [
        ([(10, 8), (230, 2)], "motorway"),
        ([(10, 5), (210, 5)], "recommended"),
        ([(10, 8), (210, 2)], "not_recommended"),
        ([(10, 12), (210, 2.5), (20, 5)], "run"),
        ([(10, 14), (200, 6)], "built_up"),
        ([(10, 10), (11, 1), (10, 2)], "reuse"),
    ],
)
def test_a_loop_that_fails_a_check_says_which(
    store: ScoreStore, parts: list[tuple[int, float]], reason: str
) -> None:
    assert check(store, edges_of(*parts)) == reason


def test_a_run_of_unrecommended_road_is_measured_in_one_stretch(store: ScoreStore) -> None:
    # Two 1.5 km pieces with good road between them are fine; side by side they are not.
    apart = edges_of((10, 10), (210, 1.5), (20, 10), (210, 1.5), (30, 10))
    assert isinstance(check(store, apart), Loop)
    together = edges_of((10, 10), (210, 1.5), (211, 1.5), (20, 10), (30, 10))
    assert check(store, together) == "run"


def test_a_loop_must_take_the_requested_time(store: ScoreStore) -> None:
    edges = edges_of((10, 10), (20, 10))
    route = make_route(20, 50 * CONFIG.speed_factor)
    assert evaluate_route(route, edges, [START], store, 60, CONFIG) == "time"
    assert isinstance(evaluate_route(route, edges, [START], store, 52, CONFIG), Loop)


def test_a_loop_must_stay_inside_the_data(store: ScoreStore) -> None:
    edges = edges_of((10, 10))
    route = Route(10, 36 * 60 * CONFIG.speed_factor, (), ((51.5, -2.19), (51.5, -1.2)))
    assert evaluate_route(route, edges, [START], store, 36, CONFIG) == "edge"


# --- choosing candidates ----------------------------------------------------------


def test_anchors_are_spread_around_the_start(store: ScoreStore, mids) -> None:
    router = FakeRouter(mids)
    outline = router.isochrone(START, 30)
    anchors = choose_anchors(START, outline, store, CONFIG)
    assert len(anchors) == 8
    assert sorted(round(a.bearing) for a in anchors) == [0, 45, 90, 135, 180, 225, 270, 315]


def test_anchors_outside_the_reach_or_too_near_the_start_are_left_out(
    store: ScoreStore, mids
) -> None:
    router = FakeRouter(mids)
    small = router.isochrone(START, 5)  # about 6 km wide: the ring is 9 km out
    assert choose_anchors(START, small, store, CONFIG) == []
    near = LoopConfig(anchor_min_separation_m=10_000)
    assert choose_anchors(START, router.isochrone(START, 30), store, near) == []


def anchors_at(bearings: list[float], score: float = 70) -> list[Anchor]:
    return [Anchor(i, ring_point(b), score, 3000, b) for i, b in enumerate(bearings)]


def test_candidates_fit_the_time_and_turn_far_enough_between_anchors(mids) -> None:
    router = FakeRouter(mids)
    anchors = anchors_at([0, 20, 120, 240])
    times = router.matrix([START, *(a.point for a in anchors)])
    # A loop of two anchors 120 degrees apart is 9 + 15.6 + 9 km at 800 m/min: 42 minutes.
    plans = plan_candidates(times, anchors, 42 * 60, CONFIG)
    assert plans
    for plan in plans:
        assert {0, 1} != set(plan.order)  # 0 and 20 degrees are too close
        assert 0.70 <= plan.estimate_s / (42 * 60) <= 1.15
    assert plan_candidates(times, anchors, 400 * 60, CONFIG) == []


def test_the_same_anchors_in_both_directions_make_one_candidate(mids) -> None:
    router = FakeRouter(mids)
    anchors = anchors_at([0, 120])
    times = router.matrix([START, *(a.point for a in anchors)])
    assert len(plan_candidates(times, anchors, 42 * 60, CONFIG)) == 1


def test_better_scored_anchors_come_first(mids) -> None:
    router = FakeRouter(mids)
    anchors = [
        Anchor(0, ring_point(0), 40, 3000, 0),
        Anchor(120, ring_point(120), 40, 3000, 120),
        Anchor(240, ring_point(240), 90, 3000, 240),
        Anchor(300, ring_point(300), 90, 3000, 300),
    ]
    times = router.matrix([START, *(a.point for a in anchors)])
    assert set(plan_candidates(times, anchors, 42 * 60, CONFIG)[0].order) == {2, 3}


# --- the whole thing ----------------------------------------------------------------


def test_generate_loops_returns_loops_that_pass_every_check(store: ScoreStore, mids) -> None:
    router = FakeRouter(mids)
    result = generate_loops(START, 45, router, store, count=3)
    assert 1 <= len(result.loops) <= 3
    scores = [loop.score for loop in result.loops]
    assert scores == sorted(scores, reverse=True)
    for loop in result.loops:
        assert abs(loop.duration_min - 45) <= 4.5
        assert loop.shares[Group.RECOMMENDED] >= 0.6
        assert loop.waypoints
        assert loop.points[0] == loop.points[-1] == START


def test_the_best_loop_goes_through_the_best_roads(tmp_path: Path) -> None:
    scores = {n: 90.0 if n in (1, 4) else 30.0 for n in range(1, 9)}
    mids = make_store(tmp_path / "s.sqlite", scores=scores)
    with ScoreStore(tmp_path / "s.sqlite") as store:
        result = generate_loops(START, 50, FakeRouter(mids), store, count=3)
    assert set(result.loops[0].waypoints) == {mids[1], mids[4]}
    assert result.loops[0].score > result.loops[-1].score


def test_a_start_near_the_edge_of_the_data_is_refused(store: ScoreStore, mids) -> None:
    with pytest.raises(OutsideRegion):
        generate_loops((51.5, -2.195), 60, FakeRouter(mids), store)


def test_no_loop_fits_when_the_time_is_too_long_for_the_roads_in_reach(
    store: ScoreStore, mids
) -> None:
    result = generate_loops(START, 400, FakeRouter(mids), store)
    assert result.loops == []
    assert result.notes


def test_the_notes_say_why_loops_were_dropped(tmp_path: Path) -> None:
    mids = make_store(tmp_path / "s.sqlite")
    with ScoreStore(tmp_path / "s.sqlite") as store:
        strict = LoopConfig(min_recommended_share=1.01)
        result = generate_loops(START, 45, FakeRouter(mids), store, config=strict)
    assert result.loops == []
    assert "had too little recommended road" in result.notes[0]


def test_candidates_slower_than_planned_are_still_found(tmp_path: Path) -> None:
    # Every routed loop takes 25% longer than the matrix said. Without correction most
    # candidates would be wasted on the time check; with it the loops still turn up.
    mids = make_store(tmp_path / "s.sqlite")
    with ScoreStore(tmp_path / "s.sqlite") as store:
        router = FakeRouter(mids, slowdown=1.25)
        result = generate_loops(START, 45, router, store, count=3)
    assert result.loops
    for loop in result.loops:
        assert abs(loop.duration_min - 45) <= 4.5
    assert result.rejected["time"] <= 6  # the first few candidates teach the correction


def test_the_anchor_constant_matches_the_store() -> None:
    assert CONFIG.anchor_min_length_m <= ANCHOR_KM * 1000
