import math

import numpy as np
import pytest

from spirited.scoring.geometry import length_m, resample, to_lonlat, to_xy, turning_radii


def test_projection_round_trips_and_has_the_right_scale() -> None:
    lonlat = np.array([[-1.0, 51.5], [-0.97, 51.45]])
    assert to_lonlat(to_xy(lonlat)) == pytest.approx(lonlat)
    # One minute of latitude is about 1852 m.
    one_minute = to_xy(np.array([[-1.0, 51.5], [-1.0, 51.5 + 1 / 60]]))
    assert length_m(one_minute) == pytest.approx(1853, rel=0.005)


def test_resample_keeps_both_ends_and_spacing() -> None:
    line = np.array([[0.0, 0.0], [95.0, 0.0]])
    points = resample(line, 10.0)
    assert points[0] == pytest.approx([0, 0])
    assert points[-1] == pytest.approx([95, 0])
    assert np.diff(points[:, 0])[:-1] == pytest.approx(np.full(len(points) - 2, 10.0))


def test_turning_radius_of_a_circle() -> None:
    angles = np.linspace(0, math.pi, 400)
    circle = np.column_stack([80 * np.cos(angles), 80 * np.sin(angles)])
    radii = turning_radii(resample(circle, 10.0))
    finite = radii[np.isfinite(radii)]
    assert finite == pytest.approx(np.full(len(finite), 80.0), rel=0.02)


def test_straight_line_has_no_finite_radius() -> None:
    line = resample(np.array([[0.0, 0.0], [500.0, 0.0]]), 10.0)
    assert np.isinf(turning_radii(line)).all()
