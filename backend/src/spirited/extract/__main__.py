"""Command line for the extract pipeline.

uv run python -m spirited.extract all       # fetch, merge, clip, filter
uv run python -m spirited.extract filter    # re-run only the safety filter
"""

from __future__ import annotations

import argparse

from spirited.extract.clip import clip, merge
from spirited.extract.fetch import fetch
from spirited.extract.roadfilter_pbf import filter_file, write_report
from spirited.region import DEFAULT_PATHS, Paths

STEPS = ("fetch", "merge", "clip", "filter")


def run_filter(paths: Paths) -> None:
    result = filter_file(paths.clipped, paths.filtered, paths.excluded_csv)
    write_report(result, paths.report)
    print(
        f"kept {result.kept} highway ways, excluded {result.excluded_total}: "
        f"{dict(result.excluded.most_common())}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="spirited.extract")
    parser.add_argument("step", choices=(*STEPS, "all"))
    parser.add_argument("--force", action="store_true", help="re-download even if up to date")
    args = parser.parse_args(argv)

    paths = DEFAULT_PATHS
    paths.root.mkdir(parents=True, exist_ok=True)
    steps = STEPS if args.step == "all" else (args.step,)
    for step in steps:
        print(f"== {step}")
        if step == "fetch":
            fetch(paths, force=args.force)
        elif step == "merge":
            merge(paths)
        elif step == "clip":
            clip(paths)
        else:
            run_filter(paths)


if __name__ == "__main__":
    main()
