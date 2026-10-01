"""Write a route as a GPX track."""

from __future__ import annotations

from collections.abc import Iterable
from xml.sax.saxutils import escape

from spirited.routing.polyline import LatLon


def to_gpx(points: Iterable[LatLon], name: str) -> str:
    trkpts = "\n".join(f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}"/>' for lat, lon in points)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="Spirited" xmlns="http://www.topografix.com/GPX/1/1">\n'
        f"  <metadata><name>{escape(name)}</name></metadata>\n"
        "  <trk>\n"
        f"    <name>{escape(name)}</name>\n"
        "    <trkseg>\n"
        f"{trkpts}\n"
        "    </trkseg>\n"
        "  </trk>\n"
        "</gpx>\n"
    )
