"""Download the county extracts from Geofabrik and record what was fetched."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from spirited.region import COUNTIES, Paths, county_url

CHUNK = 1 << 20


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_md5(url: str) -> str:
    with urllib.request.urlopen(f"{url}.md5", timeout=60) as response:
        return response.read().decode().split()[0]


def _download(url: str, target: Path) -> str | None:
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as out:
        last_modified = response.headers.get("Last-Modified")
        while chunk := response.read(CHUNK):
            out.write(chunk)
    partial.replace(target)
    return last_modified


def fetch(paths: Paths, force: bool = False) -> dict[str, dict[str, str | int | None]]:
    """Download every county, verify its checksum and write the manifest."""
    paths.downloads.mkdir(parents=True, exist_ok=True)
    sources: dict[str, dict[str, str | int | None]] = {}
    for county in COUNTIES:
        url = county_url(county)
        target = paths.downloads / f"{county}.osm.pbf"
        expected = _expected_md5(url)
        last_modified = None
        if force or not target.exists() or _md5(target) != expected:
            print(f"downloading {url}")
            last_modified = _download(url, target)
        else:
            print(f"up to date: {target.name}")
        actual = _md5(target)
        if actual != expected:
            raise RuntimeError(f"checksum mismatch for {county}: {actual} != {expected}")
        sources[county] = {
            "url": url,
            "md5": actual,
            "bytes": target.stat().st_size,
            "last_modified": last_modified,
        }
    manifest = {"fetched_at": datetime.now(UTC).isoformat(timespec="seconds"), "sources": sources}
    paths.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    return sources
