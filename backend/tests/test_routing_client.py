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
    if request.url.path == "/height" and "shape" in body:
        assert body["range"] is False
        return httpx.Response(200, json={"height": [10.0 * i for i in range(len(body["shape"]))]})
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


def test_heights_at_points(client: ValhallaClient) -> None:
    assert client.heights([(51.4, -1.0), (51.41, -1.0)]) == [0.0, 10.0]
    assert client.heights([]) == []


def test_build_asks_for_heights_in_batches(client: ValhallaClient) -> None:
    import numpy as np

    from spirited.scoring.build import valhalla_heights

    lookup = valhalla_heights(client, batch=3)
    samples = [np.array([[-1.0, 51.4]] * 4), np.array([[-1.0, 51.4]] * 2)]
    first, second = lookup(samples)
    assert first is not None and second is not None
    # Batches of 3: [0, 10, 20] then [0, 10, 20], split back into 4 and 2.
    assert first.tolist() == [0.0, 10.0, 20.0, 0.0]
    assert second.tolist() == [10.0, 20.0]


def test_isochrone_returns_the_outline_as_lat_lon(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/isochrone"
        assert body["contours"] == [{"time": 25}]
        assert body["polygons"] is True
        ring = [[-1.3, 51.4], [-1.1, 51.4], [-1.1, 51.6], [-1.3, 51.4]]
        small = [[-1.2, 51.5], [-1.19, 51.5], [-1.19, 51.51], [-1.2, 51.5]]
        features = [
            {"geometry": {"type": "Polygon", "coordinates": [small]}},
            {"geometry": {"type": "Polygon", "coordinates": [ring]}},
            {"geometry": {"type": "Point", "coordinates": [-1.2, 51.5]}},
        ]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features})

    http = httpx.Client(base_url="http://valhalla", transport=httpx.MockTransport(handler))
    outline = ValhallaClient(http=http).isochrone((51.5, -1.2), 25)
    assert outline[0] == (51.4, -1.3)  # lat first, and the larger polygon
    assert len(outline) == 4


def test_isochrone_without_a_polygon_is_an_error() -> None:
    http = httpx.Client(
        base_url="http://valhalla",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"features": []})),
    )
    with pytest.raises(ValhallaError):
        ValhallaClient(http=http).isochrone((51.5, -1.2), 25)


def test_matrix_gives_seconds_between_every_pair() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/sources_to_targets"
        assert body["sources"] == body["targets"]
        row = [{"time": 0.0}, {"time": 120.0}]
        return httpx.Response(200, json={"sources_to_targets": [row, [{"time": None}, row[0]]]})

    http = httpx.Client(base_url="http://valhalla", transport=httpx.MockTransport(handler))
    times = ValhallaClient(http=http).matrix([(51.5, -1.2), (51.6, -1.1)])
    assert times == [[0.0, 120.0], [None, 0.0]]
