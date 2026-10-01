"""Download the England extract from Geofabrik and record what was fetched."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from spirited.region import SOURCE_URL, Paths

CHUNK = 1 << 20


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _published_md5(url: str) -> str | None:
    """Geofabrik's checksum for a file, or None if it does not publish one."""
    try:
        with urllib.request.urlopen(f"{url}.md5", timeout=60) as response:
            return response.read().decode().split()[0]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def _download(url: str, target: Path) -> str | None:
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as out:
        last_modified = response.headers.get("Last-Modified")
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if total and done % (100 * CHUNK) < CHUNK:
                print(f"  {done >> 20} of {total >> 20} MB")
    partial.replace(target)
    return last_modified


def fetch(paths: Paths, force: bool = False) -> dict[str, str | int | None]:
    """Download the source extract, verify its checksum and write the manifest."""
    paths.downloads.mkdir(parents=True, exist_ok=True)
    target = paths.source
    expected = _published_md5(SOURCE_URL)
    if expected is None:
        print("Geofabrik publishes no checksum for this file; skipping verification")

    last_modified = None
    up_to_date = target.exists() and expected is not None and _md5(target) == expected
    if force or not up_to_date:
        print(f"downloading {SOURCE_URL}")
        last_modified = _download(SOURCE_URL, target)
    else:
        print(f"up to date: {target.name}")

    actual = _md5(target)
    if expected is not None and actual != expected:
        raise RuntimeError(f"checksum mismatch for {target.name}: {actual} != {expected}")
    source: dict[str, str | int | None] = {
        "url": SOURCE_URL,
        "md5": actual,
        "md5_verified": "yes" if expected else "no",
        "bytes": target.stat().st_size,
        "last_modified": last_modified,
    }
    manifest = {"fetched_at": datetime.now(UTC).isoformat(timespec="seconds"), "source": source}
    paths.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    return source
