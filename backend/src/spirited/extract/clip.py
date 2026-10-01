"""Clip the England extract to the region box with osmium-tool."""

from __future__ import annotations

import shutil
import subprocess

from spirited.region import CLIP_BOX, BBox, Paths


def _osmium() -> str:
    exe = shutil.which("osmium")
    if exe is None:
        raise RuntimeError("osmium-tool is not installed or not on PATH; see the README")
    return exe


def clip(paths: Paths, box: BBox = CLIP_BOX) -> None:
    subprocess.run(
        [
            _osmium(),
            "extract",
            "--bbox",
            box.as_osmium_arg(),
            # "smart" with boundary relations keeps the England and UK boundaries
            # whole, so Valhalla can build its admin areas (driving on the left,
            # UK access rules). "complete_ways" cut them and Valhalla dropped them.
            "--strategy",
            "smart",
            "--option",
            "types=multipolygon,boundary",
            "--set-bounds",
            str(paths.source),
            "-o",
            str(paths.clipped),
            "--overwrite",
        ],
        check=True,
    )
