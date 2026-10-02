"""Build road scores, or rank the reference roads.

uv run python -m spirited.scoring build [--no-heights]
uv run python -m spirited.scoring evaluate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spirited.region import DEFAULT_PATHS
from spirited.routing.client import ValhallaClient
from spirited.scoring import build, evaluate
from spirited.scoring.store import ScoreStore


def _build(args: argparse.Namespace) -> int:
    source: Path = args.source
    if not source.exists():
        print(f"{source} not found: run `make extract` first", file=sys.stderr)
        return 1
    with ValhallaClient() as client:
        if args.no_heights:
            heights = None
            print("Skipping heights: elevation will score 0 with no confidence.")
        elif not client.is_up():
            print(
                "Valhalla is not running, and heights come from it. Start it with "
                "`make routing`, or pass --no-heights.",
                file=sys.stderr,
            )
            return 1
        else:
            heights = build.valhalla_heights(client)
        print(f"Scoring roads in {source.name} ...")
        scores = build.build(source, args.out, heights)
    print(json.dumps(build.summary(scores), indent=2))
    print(f"wrote {args.out}")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    roads = evaluate.load_references(args.refs)
    ready = [road for road in roads if not road.is_placeholder]
    if not ready:
        print(f"No reference roads yet: fill in the placeholders in {args.refs}.")
        return 1
    print(f"{len(ready)} reference roads ({len(roads) - len(ready)} placeholders skipped)")
    excluded = None
    if not args.skip_nearby:
        print("Indexing roads removed by the safety filter ...")
        excluded = evaluate.ExcludedIndex.load(DEFAULT_PATHS.excluded_csv, DEFAULT_PATHS.clipped)
    with ValhallaClient() as client, ScoreStore(args.scores) as store:
        if not client.is_up():
            print("Valhalla is not running: start it with `make routing`.", file=sys.stderr)
            return 1
        reports = evaluate.evaluate(ready, client, store, excluded)
    text = evaluate.format_report(reports)
    print()
    print(text)
    if args.out:
        args.out.write_text(text + "\n")
        print(f"\nwrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spirited.scoring")
    commands = parser.add_subparsers(dest="command", required=True)

    build_cmd = commands.add_parser("build", help="score every road and write scores.sqlite")
    build_cmd.add_argument("--source", type=Path, default=DEFAULT_PATHS.filtered)
    build_cmd.add_argument("--out", type=Path, default=build.SCORES_PATH)
    build_cmd.add_argument(
        "--no-heights", action="store_true", help="skip Valhalla; elevation scores 0"
    )
    build_cmd.set_defaults(run=_build)

    eval_cmd = commands.add_parser("evaluate", help="rank the reference roads")
    eval_cmd.add_argument("--refs", type=Path, default=evaluate.REFERENCE_PATH)
    eval_cmd.add_argument("--scores", type=Path, default=build.SCORES_PATH)
    eval_cmd.add_argument("--out", type=Path, help="also write the report to this file")
    eval_cmd.add_argument(
        "--skip-nearby", action="store_true", help="skip the check for removed roads nearby"
    )
    eval_cmd.set_defaults(run=_evaluate)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
