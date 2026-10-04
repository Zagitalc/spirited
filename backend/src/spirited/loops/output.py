"""A loop as plain data: the shape `POST /loops` returns and `make loops` draws."""

from __future__ import annotations

from typing import Any

from spirited.loops.generate import Group, Loop
from spirited.loops.viewer import segment_paths
from spirited.routing import polyline
from spirited.routing.gpx import to_gpx


def loop_to_dict(loop: Loop, name: str = "Spirited loop", with_gpx: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "distance_km": round(loop.distance_km, 1),
        "duration_min": round(loop.duration_min),
        "score": round(loop.score, 1),
        "shares": {group.value: round(loop.shares[group], 3) for group in Group},
        "reuse_share": round(loop.reuse_share, 3),
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat] for lat, lon in loop.points],
        },
        "polyline": polyline.encode(loop.points),
        "segments": [
            {
                "from_km": round(s.from_km, 2),
                "to_km": round(s.to_km, 2),
                "road": s.road,
                "group": s.group.value,
                "score": s.score,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lat, lon in piece["path"]],
                },
            }
            for s, piece in zip(loop.segments, segment_paths(loop), strict=True)
        ],
        "warnings": list(loop.warnings),
    }
    if with_gpx:
        data["gpx"] = to_gpx(loop.points, name=name)
    return data
