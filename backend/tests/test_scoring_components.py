"""The scoring rules on hand-made roads, where the right answer is obvious."""

import math

import numpy as np
import pytest

from spirited.scoring import components as c
from spirited.scoring.components import Component, Ineligible, Part


def s_bends(length_m: float, amplitude_m: float, wavelength_m: float) -> np.ndarray:
    x = np.linspace(0, length_m, int(length_m / 5) + 1)
    return np.column_stack([x, amplitude_m * np.sin(2 * math.pi * x / wavelength_m)])


def test_straight_road_has_no_curvature() -> None:
    assert c.bends_per_km(np.array([[0.0, 0.0], [3000.0, 0.0]])) == 0


def test_a_single_sharp_kink_is_not_a_bend() -> None:
    # A right-angle corner drawn with one node: tight, but over only a few metres.
    corner = np.array([[0.0, 0.0], [1000.0, 0.0], [1000.0, 1000.0]])
    assert c.bends_per_km(corner) == 0


def test_a_gentle_sweep_is_not_a_bend() -> None:
    angles = np.linspace(0, math.pi / 2, 200)
    sweep = np.column_stack([500 * np.cos(angles), 500 * np.sin(angles)])
    assert c.bends_per_km(sweep) == 0


def test_sustained_s_bends_score_highly() -> None:
    # Bends of about 100 m radius one after another, for 2 km.
    bends = c.bends_per_km(s_bends(2000, amplitude_m=40, wavelength_m=400))
    assert bends > c.FULL_CURVATURE_M_PER_KM
    assert c.curvature_score(bends) == 1


def test_more_bends_score_more() -> None:
    sparse = c.bends_per_km(
        np.concatenate([s_bends(400, 40, 400), [[400 + d, 0.0] for d in (500, 1600)]])
    )
    dense = c.bends_per_km(s_bends(2000, 40, 400))
    assert 0 < sparse < dense


@pytest.mark.parametrize(
    ("highway", "mph", "reason"),
    [
        ("residential", 60, Ineligible.ROAD_CLASS),
        ("service", 60, Ineligible.ROAD_CLASS),
        ("living_street", 60, Ineligible.ROAD_CLASS),
        ("motorway", 70, Ineligible.ROAD_CLASS),
        ("primary_link", 60, Ineligible.SLIP_ROAD),
        ("tertiary", 30, Ineligible.SPEED_LIMIT),
        ("secondary", 20, Ineligible.SPEED_LIMIT),
        ("unclassified", 30.2, Ineligible.SPEED_LIMIT),  # 48 km/h tagged in km/h
        ("tertiary", 40, None),
        ("trunk", 70, None),
    ],
)
def test_eligibility(highway: str, mph: float, reason: Ineligible | None) -> None:
    assert c.ineligible_reason(highway, mph) == reason


def test_road_class_order() -> None:
    order = ["tertiary", "secondary", "primary", "trunk"]
    scores = [c.road_class_score(h) for h in order]
    assert scores == sorted(scores, reverse=True)
    assert c.road_class_score("motorway") == 0


def test_speed_score_points() -> None:
    assert c.speed_score(60) == 1
    assert c.speed_score(50) == pytest.approx(0.7)
    assert c.speed_score(40) == pytest.approx(0.3)
    assert c.speed_score(30) == 0
    assert c.speed_score(70) == pytest.approx(0.8)


def test_junction_and_settlement_scores_fall_with_density() -> None:
    assert c.junction_score(1) == 1
    assert c.junction_score(6) == pytest.approx(0.5)
    assert c.junction_score(12) == 0
    assert c.settlement_score(0.05) == 1
    assert c.settlement_score(0.8) == 0


def test_smoothing_removes_phantom_climb_from_noisy_flat_ground() -> None:
    rng = np.random.default_rng(7)
    flat = 100 + rng.normal(0, 4, 200)  # 10 km of flat road with 4 m of noise
    assert c.climb_m(flat, threshold_m=0) > 300  # what raw data claims
    assert c.climb_m(c.smooth_heights(flat)) < 25  # under 2.5 m per km


def test_smoothing_keeps_most_of_a_real_climb() -> None:
    rng = np.random.default_rng(7)
    x = np.arange(200) * c.HEIGHT_STEP_M
    true = 100 + 30 * np.sin(x / 1500)
    measured = c.climb_m(c.smooth_heights(true + rng.normal(0, 4, len(x))))
    assert measured == pytest.approx(c.climb_m(true, threshold_m=0), rel=0.25)


def test_combine_weights_scores_and_confidence() -> None:
    perfect = {name: Part(1.0, 1.0) for name in Component}
    assert c.combine(perfect) == pytest.approx((100, 1))
    unsure_speed = {**perfect, Component.SPEED: Part(1.0, 0.3)}
    _, confidence = c.combine(unsure_speed)
    assert confidence == pytest.approx(1 - c.WEIGHTS[Component.SPEED] * 0.7)


def test_sparse_geometry_lowers_curvature_confidence() -> None:
    assert c.curvature_confidence(10) == 1
    assert c.curvature_confidence(300) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("tags", "narrow"),
    [
        ({"highway": "tertiary", "lanes": "1"}, 1),
        ({"highway": "tertiary", "width": "3.5"}, 1),
        ({"highway": "tertiary", "width": "3.5 m"}, 1),
        ({"highway": "tertiary", "est_width": "4"}, 1),
        ({"highway": "tertiary", "lanes": "1", "oneway": "yes"}, 0),  # one side of a dual road
        ({"highway": "tertiary"}, 0),
        ({"highway": "unclassified"}, 0.5),  # possibly narrow: no evidence either way
        ({"highway": "unclassified", "lanes": "2"}, 0.5),  # lanes=2 is often a default
        ({"highway": "tertiary", "lanes": "2"}, 0),
        ({"highway": "unclassified", "width": "6"}, 0),
        ({"highway": "unclassified", "width": "12'"}, 0.5),  # feet are not parsed
        ({"highway": "unclassified", "lanes": "1"}, 1),
    ],
)
def test_narrowness_from_tags(tags: dict[str, str], narrow: float) -> None:
    assert c.narrowness(tags) == narrow


def test_narrow_factor_scales_with_share() -> None:
    assert c.narrow_factor(0) == 1
    assert c.narrow_factor(1) == pytest.approx(c.NARROW_SCORE_FACTOR)
    assert c.narrow_factor(0.5) == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"highway": "primary", "oneway": "yes", "ref": "A4"}, True),
        ({"highway": "trunk", "oneway": "-1"}, True),
        ({"highway": "primary", "dual_carriageway": "yes"}, True),
        ({"highway": "primary", "expressway": "yes"}, True),
        ({"highway": "primary", "ref": "A329"}, False),
        ({"highway": "tertiary", "oneway": "yes"}, False),
        ({"highway": "secondary", "oneway": "yes"}, False),
    ],
)
def test_dual_carriageway_detection(tags: dict[str, str], expected: bool) -> None:
    assert c.is_dual_carriageway(tags) is expected
