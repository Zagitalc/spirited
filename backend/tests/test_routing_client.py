"""The Valhalla client against a fake server, using hand-written responses in
Valhalla's format. No Valhalla needed."""

import json

import httpx
import pytest

from spirited.routing import polyline
from spirited.routing.client import ValhallaClient, ValhallaError

LEG_1 = [(51.4545, -0.9781), (51.43, -1.10)]
LEG_2 = [(51.43, -1.10), (51.4014, -1.3231)]


def fake_valhalla(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content) if request.content else {}
    if request.url.path == "/route":
        if body["locations"][0]["lat"] > 90:
            return httpx.Response(400, json={"error": "No suitable edges near location"})
        assert body["costing"] == "auto"
        assert body["costing_options"]["auto"]["exclude_unpaved"] is True
        return httpx.Response(
            200,
            json={
                "trip": {
                    "summary": {"length": 31.2, "time": 1980.0},
                    "legs": [
                        {"shape": polyline.encode(LEG_1)},
                        {"shape": polyline.encode(LEG_2)},
                    ],
                }
            },
        )
    if request.url.path == "/trace_attributes":
        assert body["shape_match"] == "edge_walk"
        way = 100 if polyline.decode(body["encoded_polyline"]) == pytest.approx(LEG_1) else 200
        return httpx.Response(
            200,
            json={"edges": [{"way_id": way, "names": ["A4", "Bath Road"], "length": 1.5}]},
        )
    if request.url.path == "/height":
        assert body["range"] is True
        return httpx.Response(200, json={"range_height": [[0, 40.0], [30, 45.5], [60, None]]})
    return httpx.Response(404)


@pytest.fixture
def client() -> ValhallaClient:
    http = httpx.Client(base_url="http://valhalla", transport=httpx.MockTransport(fake_valhalla))
    return ValhallaClient(http=http)


def test_route_joins_legs_without_repeating_the_shared_point(client: ValhallaClient) -> None:
    route = client.route([LEG_1[0], LEG_1[1], LEG_2[1]])
    assert route.distance_km == 31.2
    assert route.duration_min == 33
    assert list(route.points) == pytest.approx([LEG_1[0], LEG_1[1], LEG_2[1]])


def test_way_ids_cover_every_leg(client: ValhallaClient) -> None:
    route = client.route([LEG_1[0], LEG_1[1], LEG_2[1]])
    assert client.way_ids(route) == {100, 200}
    assert client.edges(route)[0].names == ("A4", "Bath Road")


def test_elevation_skips_points_without_data(client: ValhallaClient) -> None:
    route = client.route([LEG_1[0], LEG_2[1]])
    assert client.elevation(route) == [(0.0, 40.0), (30.0, 45.5)]


def test_errors_are_raised_with_valhallas_message(client: ValhallaClient) -> None:
    with pytest.raises(ValhallaError, match="No suitable edges"):
        client.route([(99.0, 0.0), (51.4, -1.3)])


def test_a_route_needs_two_points(client: ValhallaClient) -> None:
    with pytest.raises(ValueError):
        client.route([(51.4, -1.3)])
