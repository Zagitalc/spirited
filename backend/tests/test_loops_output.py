"""Loops as data, as a map page, and over HTTP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from loop_support import START, FakeRouter, make_store

from spirited import api
from spirited.loops import viewer
from spirited.loops.generate import Group, Loop, generate_loops
from spirited.loops.output import loop_to_dict
from spirited.routing import polyline
from spirited.scoring.store import ScoreStore


@pytest.fixture
def loop(tmp_path: Path) -> Loop:
    mids = make_store(tmp_path / "scores.sqlite")
    with ScoreStore(tmp_path / "scores.sqlite") as store:
        result = generate_loops(START, 45, FakeRouter(mids), store, count=1)
    return result.loops[0]


def test_a_loop_becomes_plain_data(loop: Loop) -> None:
    data = loop_to_dict(loop, name="Loop 1")
    assert set(data["shares"]) == {g.value for g in Group}
    first = data["geometry"]["coordinates"][0]
    assert first == [START[1], START[0]]  # GeoJSON is lon, lat
    assert polyline.decode(data["polyline"])[0] == pytest.approx(START)
    assert data["gpx"].startswith("<?xml") and "<name>Loop 1</name>" in data["gpx"]
    assert data["segments"][0]["from_km"] == 0
    assert data["segments"][-1]["to_km"] == pytest.approx(loop.distance_km, abs=0.1)
    json.dumps(data)  # nothing in it needs a custom encoder


def test_without_gpx_the_field_is_left_out(loop: Loop) -> None:
    assert "gpx" not in loop_to_dict(loop, with_gpx=False)


def test_every_segment_gets_part_of_the_line(loop: Loop) -> None:
    paths = viewer.segment_paths(loop)
    assert len(paths) == len(loop.segments)
    assert all(len(p["path"]) >= 2 for p in paths)
    assert paths[0]["path"][0] == list(loop.points[0])


def test_the_map_page_carries_the_loops_and_the_attribution(loop: Loop) -> None:
    page = viewer.render(START, 45, [loop], ["a note </script>"])
    assert "OpenStreetMap" in page
    assert "const DATA = " in page
    assert "</script>" not in page.split("const DATA = ")[1].split("\n")[0]
    data = json.loads(page.split("const DATA = ")[1].split(";\n")[0].replace("<\\/", "</"))
    assert data["loops"][0]["km"] == round(loop.distance_km, 1)
    assert data["notes"] == ["a note </script>"]


# --- HTTP -------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path):
    mids = make_store(tmp_path / "scores.sqlite")

    def router():
        yield FakeRouter(mids)

    def store():
        with ScoreStore(tmp_path / "scores.sqlite") as s:
            yield s

    api.app.dependency_overrides[api.get_router] = router
    api.app.dependency_overrides[api.get_store] = store
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def body(**changes: object) -> dict[str, object]:
    return {"start": {"lat": START[0], "lon": START[1]}, "duration_min": 45, **changes}


def test_post_loops_returns_loops(client: TestClient) -> None:
    response = client.post("/loops", json=body(count=2))
    assert response.status_code == 200
    data = response.json()
    assert 1 <= len(data["loops"]) <= 2
    first = data["loops"][0]
    assert first["geometry"]["type"] == "LineString"
    assert first["gpx"].startswith("<?xml")
    assert set(first["shares"]) == {"recommended", "not_recommended", "built_up"}
    assert isinstance(data["notes"], list)


# The fields below are the contract in docs/api.md. A client (the Android app) depends on
# every one of them, so a change here has to be deliberate: edit this test, the docs and
# the client together.
LOOP_FIELDS = {
    "distance_km",
    "duration_min",
    "score",
    "shares",
    "reuse_share",
    "geometry",
    "polyline",
    "gpx",
    "segments",
    "warnings",
}
SEGMENT_FIELDS = {"from_km", "to_km", "road", "group", "score", "geometry"}


def test_the_response_has_exactly_the_documented_fields(client: TestClient) -> None:
    data = client.post("/loops", json=body(count=2)).json()
    assert set(data) == {"loops", "notes"}
    assert data["loops"]
    for loop in data["loops"]:
        assert set(loop) == LOOP_FIELDS
        assert set(loop["shares"]) == {"recommended", "not_recommended", "built_up"}
        assert loop["segments"]
        for segment in loop["segments"]:
            assert set(segment) == SEGMENT_FIELDS
            assert segment["group"] in {"recommended", "not_recommended", "built_up"}
            assert segment["geometry"]["type"] == "LineString"
            assert len(segment["geometry"]["coordinates"]) >= 2


def test_segment_geometries_follow_the_loop_in_order(client: TestClient) -> None:
    loop = client.post("/loops", json=body()).json()["loops"][0]
    whole = loop["geometry"]["coordinates"]
    pieces = [c for s in loop["segments"] for c in s["geometry"]["coordinates"]]
    # Pieces may share their joining points, but together they start and end where the
    # loop does and never leave it.
    assert pieces[0] == whole[0]
    assert pieces[-1] == whole[-1]
    assert {tuple(c) for c in pieces} <= {tuple(c) for c in whole}


def test_post_loops_with_no_loop_found_is_still_ok_and_says_why(client: TestClient) -> None:
    response = client.post("/loops", json=body(duration_min=240))
    assert response.status_code == 200
    assert response.json()["loops"] == []
    assert response.json()["notes"]


@pytest.mark.parametrize(
    "change",
    [{"duration_min": 5}, {"duration_min": 500}, {"count": 0}, {"start": {"lat": 99, "lon": 0}}],
)
def test_post_loops_rejects_nonsense(client: TestClient, change: dict[str, object]) -> None:
    assert client.post("/loops", json=body(**change)).status_code == 422


def test_a_start_outside_the_area_is_422(client: TestClient) -> None:
    far = body(start={"lat": 51.5, "lon": -2.199})
    response = client.post("/loops", json=far)
    assert response.status_code == 422
    assert "edge" in response.json()["detail"]


def test_missing_services_are_503(tmp_path: Path) -> None:
    def down():
        raise HTTPException(503, "The routing service is not running.")
        yield

    api.app.dependency_overrides[api.get_router] = down
    try:
        response = TestClient(api.app).post("/loops", json=body())
    finally:
        api.app.dependency_overrides.clear()
    assert response.status_code == 503
