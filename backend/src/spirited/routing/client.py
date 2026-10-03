"""A small Valhalla client: routes, the OSM ways a route uses, and its elevation."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import httpx

from spirited.routing import polyline
from spirited.routing.costing import COSTING, costing_options
from spirited.routing.polyline import LatLon

DEFAULT_URL = "http://localhost:8002"


class ValhallaError(RuntimeError):
    """Valhalla returned an error, for example because no route exists."""


@dataclass(frozen=True)
class Route:
    distance_km: float
    duration_s: float
    # One encoded polyline (precision 6) per leg, exactly as Valhalla returned it.
    leg_shapes: tuple[str, ...]
    points: tuple[LatLon, ...] = field(repr=False)

    @property
    def duration_min(self) -> float:
        return self.duration_s / 60


@dataclass(frozen=True)
class Edge:
    way_id: int
    names: tuple[str, ...]
    length_km: float
    # Where the edge begins and ends. A long OSM way is many edges, so the way id alone
    # cannot tell a road driven twice from a road driven on for another stretch.
    ends: tuple[LatLon, LatLon] | None = None

    @property
    def key(self) -> tuple[object, ...]:
        """The same for an edge driven either way, so a road used twice has one key."""
        if self.ends is None:
            return (self.way_id,)
        a, b = (tuple(round(v, 5) for v in end) for end in self.ends)
        return (self.way_id, *sorted([a, b]))


def _ring_area(ring: list[list[float]]) -> float:
    """Shoelace area of a (lon, lat) ring, enough to tell which of two is bigger."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(ring)) / 2)


class ValhallaClient:
    def __init__(self, base_url: str | None = None, http: httpx.Client | None = None) -> None:
        url = base_url or os.environ.get("VALHALLA_URL", DEFAULT_URL)
        self._http = http or httpx.Client(base_url=url, timeout=30)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ValhallaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post(path, json=body)
        data = response.json()
        if response.status_code != 200 or "error" in data:
            message = data.get("error", response.text)
            raise ValhallaError(f"{path} failed ({response.status_code}): {message}")
        return data

    def is_up(self) -> bool:
        try:
            return self._http.get("/status").status_code == 200
        except httpx.HTTPError:
            return False

    def route(self, points: list[LatLon], avoid: Sequence[LatLon] = ()) -> Route:
        """A car route through the points, in order. Each `avoid` point excludes the road
        nearest to it, in both directions."""
        if len(points) < 2:
            raise ValueError("a route needs at least two points")
        body = {
            "locations": [{"lat": lat, "lon": lon} for lat, lon in points],
            "costing": COSTING,
            "costing_options": costing_options(),
            "units": "kilometers",
            "directions_type": "none",
        }
        if avoid:
            body["exclude_locations"] = [{"lat": lat, "lon": lon} for lat, lon in avoid]
        trip = self._post("/route", body)["trip"]
        shapes = tuple(leg["shape"] for leg in trip["legs"])
        decoded: list[LatLon] = []
        for shape in shapes:
            leg_points = polyline.decode(shape)
            # Each leg starts where the previous one ended; keep that point once.
            decoded.extend(leg_points[1:] if decoded else leg_points)
        summary = trip["summary"]
        return Route(
            distance_km=float(summary["length"]),
            duration_s=float(summary["time"]),
            leg_shapes=shapes,
            points=tuple(decoded),
        )

    def isochrone(self, start: LatLon, minutes: float) -> list[LatLon]:
        """The outline (lat, lon) of everywhere reachable from `start` in `minutes`."""
        body = {
            "locations": [{"lat": start[0], "lon": start[1]}],
            "costing": COSTING,
            "costing_options": costing_options(),
            "contours": [{"time": minutes}],
            "polygons": True,
            "denoise": 0.5,
        }
        data = self._post("/isochrone", body)
        rings = [
            feature["geometry"]["coordinates"][0]
            for feature in data.get("features", [])
            if feature["geometry"]["type"] == "Polygon"
        ]
        if not rings:
            raise ValhallaError(f"no isochrone around {start}: is it on a road?")
        ring = max(rings, key=_ring_area)
        return [(float(lat), float(lon)) for lon, lat in ring]

    def matrix(self, points: list[LatLon]) -> list[list[float | None]]:
        """Drive time in seconds from each point to each other point (None: no route)."""
        locations = [{"lat": lat, "lon": lon} for lat, lon in points]
        body = {
            "sources": locations,
            "targets": locations,
            "costing": COSTING,
            "costing_options": costing_options(),
        }
        data = self._post("/sources_to_targets", body)
        return [
            [None if cell.get("time") is None else float(cell["time"]) for cell in row]
            for row in data["sources_to_targets"]
        ]

    def edges(self, route: Route) -> list[Edge]:
        """Every graph edge the route uses, with its OSM way id, in order."""
        edges: list[Edge] = []
        for shape in route.leg_shapes:
            body = {
                "encoded_polyline": shape,
                "costing": COSTING,
                "costing_options": costing_options(),
                "shape_match": "edge_walk",
                "filters": {
                    "attributes": [
                        "shape",
                        "edge.way_id",
                        "edge.names",
                        "edge.length",
                        "edge.begin_shape_index",
                        "edge.end_shape_index",
                    ],
                    "action": "include",
                },
            }
            data = self._post("/trace_attributes", body)
            shape = polyline.decode(data["shape"]) if data.get("shape") else []
            for edge in data.get("edges", []):
                begin, end = edge.get("begin_shape_index"), edge.get("end_shape_index")
                ends = (
                    (shape[begin], shape[end])
                    if begin is not None and end is not None and end < len(shape)
                    else None
                )
                edges.append(
                    Edge(
                        way_id=int(edge["way_id"]),
                        names=tuple(edge.get("names", ())),
                        length_km=float(edge.get("length", 0.0)),
                        ends=ends,
                    )
                )
        return edges

    def way_ids(self, route: Route) -> set[int]:
        return {edge.way_id for edge in self.edges(route)}

    def heights(self, points: list[LatLon]) -> list[float | None]:
        """Terrain height in metres at each point, or None where there is no data."""
        if not points:
            return []
        body = {"shape": [{"lat": lat, "lon": lon} for lat, lon in points], "range": False}
        data = self._post("/height", body)
        return [None if h is None else float(h) for h in data.get("height", [])]

    def elevation(self, route: Route, every_m: int = 30) -> list[tuple[float, float]]:
        """(distance along the route in metres, height in metres) every `every_m` metres."""
        body = {
            "encoded_polyline": polyline.encode(route.points),
            "range": True,
            "resample_distance": every_m,
        }
        data = self._post("/height", body)
        return [(float(d), float(h)) for d, h in data.get("range_height", []) if h is not None]
