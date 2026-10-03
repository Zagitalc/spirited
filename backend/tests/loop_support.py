"""A made-up score database and router for the loop tests: eight good roads on a ring
around Newbury-ish, each a way with its own corridor. No Valhalla needed."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

import numpy as np

from spirited.routing.client import Edge, Route
from spirited.routing.polyline import LatLon
from spirited.scoring.geometry import to_lonlat, to_xy

START: LatLon = (51.5, -1.2)
RING_M = 9000.0
ANCHOR_KM = 3.0
SPEED_M_PER_MIN = 800.0  # 48 km/h


def ring_point(bearing_deg: float, radius_m: float = RING_M) -> LatLon:
    x0, y0 = to_xy(np.array([[START[1], START[0]]]))[0]
    angle = math.radians(bearing_deg)
    lon, lat = to_lonlat(
        np.array([[x0 + radius_m * math.sin(angle), y0 + radius_m * math.cos(angle)]])
    )[0]
    return float(lat), float(lon)


def make_store(path: Path, scores: dict[int, float] | None = None) -> dict[int, LatLon]:
    """Write corridors 1..8 at bearings 0, 45, ..., 315 and return their midpoints."""
    scores = scores or {}
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE corridors (
            id INTEGER PRIMARY KEY, highway TEXT, label TEXT, length_m REAL,
            ineligible TEXT, confidence REAL, score REAL
        );
        CREATE TABLE anchors (corridor_id INTEGER, lon REAL, lat REAL);
        CREATE TABLE corridor_ways (way_id INTEGER PRIMARY KEY, corridor_id INTEGER);
        """
    )
    mids: dict[int, LatLon] = {}
    for i in range(8):
        corridor = i + 1
        lat, lon = ring_point(45 * i)
        mids[corridor] = (lat, lon)
        db.execute(
            "INSERT INTO corridors VALUES (?, 'tertiary', ?, ?, NULL, 0.9, ?)",
            (corridor, f"B{4000 + corridor}", ANCHOR_KM * 1000, scores.get(corridor, 70.0)),
        )
        db.execute("INSERT INTO anchors VALUES (?, ?, ?)", (corridor, lon, lat))
        for n in range(6):  # a corridor is several ways, so a loop can use different ones
            db.execute("INSERT INTO corridor_ways VALUES (?, ?)", (corridor * 10 + n, corridor))
    # Corridors 20 to 24 are the ordinary kinds of road a route passes through.
    kinds = {
        20: ("residential", "road_class", None, 0.0),
        21: ("tertiary", None, 0.4, 20.0),  # low confidence
        22: ("primary", "dual_carriageway", None, 0.0),
        23: ("motorway", "road_class", None, 0.0),
        24: ("tertiary", "speed_limit", None, 0.0),
    }
    for corridor, (highway, ineligible, confidence, score) in kinds.items():
        db.execute(
            "INSERT INTO corridors VALUES (?, ?, 'X', 1000, ?, ?, ?)",
            (corridor, highway, ineligible, confidence if confidence is not None else 0.9, score),
        )
        db.execute("INSERT INTO corridor_ways VALUES (?, ?)", (corridor * 10, corridor))
    db.commit()
    db.close()
    return mids


def metres(a: LatLon, b: LatLon) -> float:
    xy = to_xy(np.array([[a[1], a[0]], [b[1], b[0]]]))
    return float(np.hypot(*(xy[1] - xy[0])))


class FakeRouter:
    """Straight-line routing at a fixed speed. Each leg is one edge, on the corridor
    nearest the leg's destination (or the start's own connector when it ends there)."""

    def __init__(self, mids: dict[int, LatLon], slowdown: float = 1.0) -> None:
        self.mids = mids
        self.slowdown = slowdown  # routed time over matrix time, as detours cause in life
        self.routed: list[list[LatLon]] = []
        self.edges_made = 0

    def isochrone(self, start: LatLon, minutes: float) -> list[LatLon]:
        far = minutes * SPEED_M_PER_MIN
        corners = [(-1, -1), (-1, 1), (1, 1), (1, -1), (-1, -1)]
        return [ring_point(math.degrees(math.atan2(dx, dy)) % 360, far * 1.5) for dx, dy in corners]

    def matrix(self, points: list[LatLon]) -> list[list[float | None]]:
        return [[metres(a, b) / SPEED_M_PER_MIN * 60 for b in points] for a in points]

    def route(self, points: list[LatLon], avoid: Sequence[LatLon] = ()) -> Route:
        self.routed.append(points)
        distance = sum(metres(a, b) for a, b in pairwise(points))
        return Route(
            distance_km=distance / 1000,
            duration_s=distance / SPEED_M_PER_MIN * 60 * self.slowdown,
            leg_shapes=(),
            points=tuple(points),
        )

    def edges(self, route: Route) -> list[Edge]:
        edges = []
        for a, b in pairwise(route.points):
            n = self.edges_made % 6
            self.edges_made += 1
            target = min(
                self.mids, key=lambda k: min(metres(self.mids[k], a), metres(self.mids[k], b))
            )
            edges.append(Edge(target * 10 + n, ("B road",), metres(a, b) / 1000))
        return edges
