"""Route between points from the command line, for checking routes by eye.

uv run python -m spirited.routing 51.4545,-0.9781 51.4014,-1.3231 --gpx route.gpx
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

from spirited.routing.client import ValhallaClient
from spirited.routing.gpx import to_gpx
from spirited.routing.polyline import LatLon


def _point(text: str) -> LatLon:
    lat, lon = (float(part) for part in text.split(","))
    return lat, lon


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="spirited.routing")
    parser.add_argument("points", nargs="+", type=_point, help="lat,lon (two or more)")
    parser.add_argument("--gpx", type=Path, help="write the route to this GPX file")
    args = parser.parse_args(argv)

    with ValhallaClient() as client:
        route = client.route(args.points)
        edges = client.edges(route)
        heights = client.elevation(route)

    print(f"{route.distance_km:.1f} km, {route.duration_min:.0f} min, {len(edges)} edges")
    by_name: defaultdict[str, float] = defaultdict(float)
    for edge in edges:
        by_name[" / ".join(edge.names) or "(unnamed)"] += edge.length_km
    print("longest stretches:")
    for name, km in sorted(by_name.items(), key=lambda item: -item[1])[:8]:
        print(f"  {km:5.1f} km  {name}")
    if heights:
        values = [h for _, h in heights]
        climb = sum(max(0.0, b - a) for a, b in pairwise(values))
        print(f"height {min(values):.0f} to {max(values):.0f} m, {climb:.0f} m of climbing")
    if args.gpx:
        args.gpx.write_text(to_gpx(route.points, name="Spirited route"))
        print(f"wrote {args.gpx}")


if __name__ == "__main__":
    main()
