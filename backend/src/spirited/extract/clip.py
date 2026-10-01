"""Merge the county extracts and clip them to the region box with osmium-tool."""

from __future__ import annotations

import shutil
import subprocess

from spirited.region import CLIP_BOX, COUNTIES, BBox, Paths


def _osmium() -> str:
    exe = shutil.which("osmium")
    if exe is None:
        raise RuntimeError("osmium-tool is not installed or not on PATH; see the README")
    return exe


def merge(paths: Paths) -> None:
    inputs = [str(paths.downloads / f"{county}.osm.pbf") for county in COUNTIES]
    subprocess.run(
        [_osmium(), "merge", *inputs, "-o", str(paths.merged), "--overwrite"], check=True
    )


def clip(paths: Paths, box: BBox = CLIP_BOX) -> None:
    subprocess.run(
        [
            _osmium(),
            "extract",
            "--bbox",
            box.as_osmium_arg(),
            "--strategy",
            "complete_ways",
            "--set-bounds",
            str(paths.merged),
            "-o",
            str(paths.clipped),
            "--overwrite",
        ],
        check=True,
    )
