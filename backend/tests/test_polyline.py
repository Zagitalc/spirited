import pytest

from spirited.routing import polyline

# Google's documented example, at precision 5.
GOOGLE_EXAMPLE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
GOOGLE_POINTS = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_decodes_googles_example() -> None:
    assert polyline.decode(GOOGLE_EXAMPLE, precision=5) == pytest.approx(GOOGLE_POINTS)


def test_encodes_googles_example() -> None:
    assert polyline.encode(GOOGLE_POINTS, precision=5) == GOOGLE_EXAMPLE


def test_round_trips_at_valhalla_precision() -> None:
    points = [(51.454513, -0.978130), (51.401400, -1.323100), (51.5, -1.0)]
    assert polyline.decode(polyline.encode(points)) == pytest.approx(points, abs=1e-6)
