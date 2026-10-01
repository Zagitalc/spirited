"""Command line for the extract pipeline.

uv run python -m spirited.extract all       # fetch, clip, filter, admin
uv run python -m spirited.extract filter    # re-run only the safety filter
"""

from __future__ import annotations

import argparse

from spirited.extract.admin import add_admin_boundary
from spirited.extract.clip import clip
from spirited.extract.fetch import fetch
from spirited.extract.roadfilter_pbf import filter_file, write_report
from spirited.region import DEFAULT_PATHS, SOURCE_URLS, Paths

STEPS = ("fetch", "clip", "filter", "admin")


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
    parser.add_argument("--url", help="download from this URL instead of the built-in mirrors")
    args = parser.parse_args(argv)

    paths = DEFAULT_PATHS
    paths.root.mkdir(parents=True, exist_ok=True)
    steps = STEPS if args.step == "all" else (args.step,)
    for step in steps:
        print(f"== {step}")
        if step == "fetch":
            fetch(paths, force=args.force, urls=[args.url] if args.url else SOURCE_URLS)
        elif step == "clip":
            clip(paths)
        elif step == "filter":
            run_filter(paths)
        else:
            add_admin_boundary(paths)
            print(f"added the UK boundary to {paths.filtered.name}")


if __name__ == "__main__":
    main()
