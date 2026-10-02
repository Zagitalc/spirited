"""Routes from the real Valhalla. Skipped unless it is running (see routing/README.md)."""

from __future__ import annotations

import csv

import pytest

from spirited.region import DEFAULT_PATHS
from spirited.routing.client import Route, ValhallaClient
from spirited.routing.polyline import LatLon

READING = (51.4560, -0.9690)
NEWBURY = (51.4014, -1.3231)
# Windsor Great Park lies between these; its roads are private for cars.
ENGLEFIELD_GREEN = (51.4300, -0.5650)
CRANBOURNE = (51.4430, -0.6700)
# The Ridgeway byway runs almost straight between these across the Downs.
WEST_ILSLEY = (51.5390, -1.3830)
LAMBOURN = (51.5085, -1.5310)

ROUTES = {
    "reading-newbury": [READING, NEWBURY],
    "windsor-great-park": [ENGLEFIELD_GREEN, CRANBOURNE],
    "ridgeway": [WEST_ILSLEY, LAMBOURN],
}


@pytest.fixture(scope="module")
def client():
    client = ValhallaClient()
    if not client.is_up():
        pytest.skip("Valhalla is not running; see routing/README.md")
    yield client
    client.close()


@pytest.fixture(scope="module")
def excluded() -> dict[int, tuple[str, str]]:
    if not DEFAULT_PATHS.excluded_csv.exists():
        pytest.skip("no excluded-ways.csv yet; run `make extract`")
    with DEFAULT_PATHS.excluded_csv.open() as handle:
        return {int(row["way_id"]): (row["reason"], row["name"]) for row in csv.DictReader(handle)}


def _route(client: ValhallaClient, points: list[LatLon]) -> Route:
    return client.route(points)


pytestmark = pytest.mark.valhalla


def test_reading_to_newbury_is_sensible(client: ValhallaClient) -> None:
    route = _route(client, ROUTES["reading-newbury"])
    assert 25 <= route.distance_km <= 45
    assert 25 <= route.duration_min <= 60
    names = {name for edge in client.edges(route) for name in edge.names}
    assert names & {"A4", "M4"}, names


def test_route_has_elevation(client: ValhallaClient) -> None:
    heights = client.elevation(_route(client, ROUTES["reading-newbury"]))
    assert len(heights) > 100
    assert all(0 < h < 400 for _, h in heights)


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_routes_never_use_an_excluded_road(
    client: ValhallaClient, excluded: dict[int, tuple[str, str]], name: str
) -> None:
    used = client.way_ids(_route(client, ROUTES[name]))
    offenders = {way: excluded[way] for way in used & excluded.keys()}
    assert offenders == {}


def test_excluded_list_contains_the_traps(excluded: dict[int, tuple[str, str]]) -> None:
    # If these are missing, the trap routes above prove nothing.
    names = {name for _, name in excluded.values()}
    assert "The Ridgeway" in names


def test_heights_cover_the_region(client: ValhallaClient) -> None:
    # Scoring needs a height for every sample point, from Swindon to Guildford.
    points = [READING, NEWBURY, WEST_ILSLEY, (51.5600, -1.7800), (51.2360, -0.5700)]
    heights = client.heights(points)
    assert all(h is not None and -10 < h < 400 for h in heights), heights
