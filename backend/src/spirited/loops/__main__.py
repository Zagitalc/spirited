"""Generate loops from the command line and look at them on a map.

uv run python -m spirited.loops 51.4545,-0.9781 --minutes 90 --out out/loops

Writes one GPX file per loop and loops.html, a page that draws them on a map.
Limits can be eased to see what they cost, e.g. --tolerance 0.2 --min-recommended 0.5.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from spirited.loops import viewer
from spirited.loops.config import LoopConfig
from spirited.loops.generate import OutsideRegion, generate_loops
from spirited.routing.client import ValhallaClient, ValhallaError
from spirited.routing.gpx import to_gpx
from spirited.routing.polyline import LatLon
from spirited.scoring.build import SCORES_PATH
from spirited.scoring.store import ScoreStore


def _point(text: str) -> LatLon:
    lat, lon = (float(part) for part in text.split(","))
    return lat, lon


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spirited.loops")
    parser.add_argument("start", type=_point, help="lat,lon")
    parser.add_argument("--minutes", type=float, default=90)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--scores", type=Path, default=SCORES_PATH)
    parser.add_argument("--out", type=Path, default=Path("out/loops"))
    # Limits that can be eased from the command line to see what they cost.
    parser.add_argument("--tolerance", type=float, help="allowed miss on time, e.g. 0.2")
    parser.add_argument("--min-recommended", type=float, dest="min_recommended_share")
    parser.add_argument("--max-not-recommended", type=float, dest="max_not_recommended_share")
    parser.add_argument("--max-built-up", type=float, dest="max_built_up_share")
    parser.add_argument("--speed-factor", type=float, dest="speed_factor")
    parser.add_argument("--town-allowance", type=float, dest="town_allowance_km")
    parser.add_argument("--max-retrace", type=float, dest="max_retrace_run_km")
    args = parser.parse_args(argv)
    names = (
        "tolerance",
        "min_recommended_share",
        "max_not_recommended_share",
        "max_built_up_share",
        "speed_factor",
        "town_allowance_km",
        "max_retrace_run_km",
    )
    changes = {n: getattr(args, n) for n in names if getattr(args, n) is not None}
    config = replace(LoopConfig(), **changes)

    with ValhallaClient() as client, ScoreStore(args.scores) as store:
        if not client.is_up():
            print("Valhalla is not running: start it with `make routing`.", file=sys.stderr)
            return 1
        try:
            result = generate_loops(args.start, args.minutes, client, store, args.count, config)
        except OutsideRegion as error:
            print(error, file=sys.stderr)
            return 1
        except ValhallaError as error:
            print(f"Valhalla could not use that start: {error}", file=sys.stderr)
            return 1

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(result.loops)} loops ({result.candidates_tried} candidates routed)")
    for n, loop in enumerate(result.loops, 1):
        shares = loop.shares
        print(
            f"  {n}. score {loop.score:5.1f}  {loop.distance_km:5.1f} km  "
            f"{loop.duration_min:4.0f} min  "
            + "  ".join(f"{g.value} {shares[g]:.0%}" for g in shares)
            + f"  repeated {loop.reuse_share:.0%}"
        )
        path = args.out / f"loop-{n}.gpx"
        path.write_text(to_gpx(loop.points, name=f"Spirited loop {n}"))
    for note in result.notes:
        print(f"note: {note}")
    page = args.out / "loops.html"
    page.write_text(viewer.render(args.start, args.minutes, result.loops, result.notes))
    print(f"wrote {page} (open it in a browser) and one GPX file per loop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
