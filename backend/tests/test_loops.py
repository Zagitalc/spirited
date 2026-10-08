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
    _longest_retrace_km,
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
    """A route that drives a square of `km` all round, starting and ending at the start."""
    side = km / 4
    dlat, dlon = side / 111.0, side / 69.5
    lat, lon = START
    corners = (
        (lat, lon),
        (lat, lon + dlon),
        (lat + dlat, lon + dlon),
        (lat + dlat, lon),
        (lat, lon),
    )
    return Route(
        distance_km=km,
        duration_s=valhalla_minutes * 60,
        leg_shapes=(),
        points=corners,
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
        ([(10, 6), (200, 7), (10, 7)], "built_up"),
        ([(10, 10), (11, 1), (10, 2)], "reuse"),
    ],
)
def test_a_loop_that_fails_a_check_says_which(
    store: ScoreStore, parts: list[tuple[int, float]], reason: str
) -> None:
    assert check(store, edges_of(*parts)) == reason


def test_built_up_road_near_the_start_and_end_is_not_held_against_a_loop(store: ScoreStore) -> None:
    # 4 km of village at each end is 40% of a 20 km loop; the way out and back is allowed.
    loop = check(store, edges_of((200, 4), (10, 12), (240, 4)))
    assert isinstance(loop, Loop)
    # What is reported still counts every kilometre.
    assert loop.shares[Group.BUILT_UP] == pytest.approx(0.4)
    assert loop.shares[Group.RECOMMENDED] == pytest.approx(0.6)
    # The same village in the middle of the loop is not excused.
    assert check(store, edges_of((10, 6), (200, 8), (10, 6))) == "built_up"
    # And only the first and last few kilometres are: more than that counts.
    assert check(store, edges_of((200, 10), (10, 10))) == "built_up"


def test_a_spur_driven_out_and_back_is_a_u_turn_however_small_a_share(store: ScoreStore) -> None:
    # 0.6 km out and 0.6 km back is only 3% of the loop, inside the reuse limit.
    spur = edges_of((10, 9), (30, 0.6), (30, 0.6), (20, 9))
    assert check(store, spur) == "retrace"
    # A quarter of a kilometre is still a U-turn: LonZac's phone test showed one that size.
    stub = edges_of((10, 9), (30, 0.25), (30, 0.25), (20, 9))
    assert check(store, stub) == "retrace"
    # Short retraces, such as turning at a junction, are fine.
    short = edges_of((10, 9), (30, 0.05), (30, 0.05), (20, 9))
    assert isinstance(check(store, short), Loop)


def test_retracing_the_street_a_loop_starts_on_is_allowed(store: ScoreStore) -> None:
    # A start on a dead end must come back out of it: the last few km are not held to the limit.
    dead_end = edges_of((30, 0.6), (10, 18), (30, 0.6))
    assert isinstance(check(store, dead_end), Loop)


def test_a_run_of_unrecommended_road_is_measured_in_one_stretch(store: ScoreStore) -> None:
    # Two 1.5 km pieces with good road between them are fine; side by side they are not.
    apart = edges_of((10, 10), (210, 1.5), (20, 10), (211, 1.5), (30, 10))
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


def test_candidates_are_ranked_with_and_without_the_expected_detour(mids) -> None:
    router = FakeRouter(mids)
    anchors = anchors_at([0, 60, 130, 200, 260, 320])
    times = router.matrix([START, *(a.point for a in anchors)])
    plans = plan_candidates(times, anchors, 42 * 60, CONFIG, scale=1.25)
    first = [p.estimate_s / 60 for p in plans[:4]]
    # Several loops of 33.7 minutes fit once 25% is added and would crowd out the rest if
    # that were the only ranking; the loops that already take 42 minutes come early too.
    assert any(m < 36 for m in first)
    assert any(m >= 42 for m in first)


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
        assert abs(loop.duration_min - 45) <= 6.75
        assert loop.shares[Group.RECOMMENDED] >= 0.6
        assert loop.waypoints
        assert loop.points[0] == loop.points[-1] == START


def test_the_best_loop_goes_through_the_best_roads(tmp_path: Path) -> None:
    scores = {n: 90.0 if n in (1, 4) else 30.0 for n in range(1, 9)}
    mids = make_store(tmp_path / "s.sqlite", scores=scores)
    with ScoreStore(tmp_path / "s.sqlite") as store:
        # No detours here: a loop that needs none must still be tried, whatever the prior.
        router = FakeRouter(mids, slowdown=1.0)
        result = generate_loops(START, 50, router, store, count=3)
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
    # Every routed loop takes 40% longer than the matrix said, more than the prior
    # expects; the loops that fit must still be found.
    mids = make_store(tmp_path / "s.sqlite")
    with ScoreStore(tmp_path / "s.sqlite") as store:
        router = FakeRouter(mids, slowdown=1.4)
        result = generate_loops(START, 45, router, store, count=3)
    assert result.loops
    for loop in result.loops:
        assert abs(loop.duration_min - 45) <= 6.75


def test_the_anchor_constant_matches_the_store() -> None:
    assert CONFIG.anchor_min_length_m <= ANCHOR_KM * 1000


def test_time_misses_are_reported_with_what_else_they_would_have_failed(tmp_path: Path) -> None:
    mids = make_store(tmp_path / "s.sqlite")
    with ScoreStore(tmp_path / "s.sqlite") as store:
        # Routing takes twice as long as planned, so every candidate misses on time.
        router = FakeRouter(mids, slowdown=2.0)
        strict = LoopConfig(min_recommended_share=1.01)
        result = generate_loops(START, 45, router, store, config=strict)
    assert result.loops == []
    assert result.rejected["time"] == result.candidates_tried
    assert result.also_fails["recommended"] == result.candidates_tried
    assert any("times the time asked" in n and "too little recommended" in n for n in result.notes)
    assert min(result.time_ratios) > 1.5


# --- a U-turn the edge list cannot show ------------------------------------------


def square_with_spur(spur_km: float, at_km: float) -> tuple[tuple[float, float], ...]:
    """A square loop of 40 km with a spur out and back `at_km` along its bottom side,
    the way back a few metres off the way out as two routed legs can be."""
    side = 10.0
    lat, lon = START
    dlat, dlon = side / 111.0, side / 69.5
    at, out = lon + at_km / 69.5, spur_km / 111.0
    jitter = 0.00003
    return (
        (lat, lon),
        (lat, at),
        (lat + out, at),
        (lat + out + jitter, at + jitter),
        (lat, at + jitter),
        (lat, lon + dlon),
        (lat + dlat, lon + dlon),
        (lat + dlat, lon),
        (lat, lon),
    )


def test_a_spur_is_found_from_the_route_shape_alone() -> None:
    assert _longest_retrace_km(square_with_spur(1.5, 5), 4.0) > 1.4
    assert _longest_retrace_km(square_with_spur(0.05, 5), 4.0) < 0.1
    assert _longest_retrace_km(square_with_spur(0.25, 5), 4.0) > 0.2
    assert _longest_retrace_km(square_with_spur(1.5, 8), 4.0) > 1.4


def test_a_spur_in_the_last_stretch_is_left_alone() -> None:
    lat, lon = START
    # Out along a dead-end street for 1.5 km and back, at the very end of a square loop.
    route = (*square_with_spur(0.0, 5)[:-1], (lat, lon + 1.5 / 69.5), (lat, lon))
    assert _longest_retrace_km(route, 4.0) == 0.0


def test_a_square_loop_has_no_retrace() -> None:
    assert _longest_retrace_km(make_route(40, 50).points, 4.0) == 0.0


def test_a_spur_whose_edges_do_not_match_is_still_rejected(store: ScoreStore) -> None:
    # Distinct way ids all round, as when the waypoint at the end of the spur splits an edge.
    kms = (8, 1.5, 1.5, 8, 8, 8, 5)
    edges = [Edge(10, ("x",), km, ends=((i, 0.0), (i, 1.0))) for i, km in enumerate(kms)]
    route = Route(40, 50 * CONFIG.speed_factor * 60, (), square_with_spur(1.5, 5))
    assert evaluate_route(route, edges, [START], store, 50, CONFIG) == "retrace"
