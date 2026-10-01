"""Download the England extract and record what was fetched."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from spirited.region import SOURCE_URLS, Paths

CHUNK = 1 << 20
# Seconds without any data before a mirror counts as stalled and the next is tried.
STALL_TIMEOUT = 60
USER_AGENT = "spirited-extract/0.1 (+https://github.com/Zagitalc/spirited)"


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=STALL_TIMEOUT)


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _published_md5(url: str) -> str | None:
    """The mirror's checksum for a file, or None if it does not publish one."""
    try:
        with _open(f"{url}.md5") as response:
            return response.read().decode().split()[0]
    except (urllib.error.URLError, TimeoutError, IndexError):
        return None


def _download(url: str, target: Path) -> str | None:
    partial = target.with_suffix(target.suffix + ".part")
    with _open(url) as response, partial.open("wb") as out:
        last_modified = response.headers.get("Last-Modified")
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if total and done % (100 * CHUNK) < CHUNK:
                print(f"  {done >> 20} of {total >> 20} MB")
    if total and done != total:
        raise OSError(f"incomplete download: {done} of {total} bytes")
    partial.replace(target)
    return last_modified


def _fetch_one(url: str, target: Path, force: bool) -> dict[str, str | int | None]:
    expected = _published_md5(url)
    if expected is None:
        print("  no checksum published here; skipping verification")
    last_modified = None
    up_to_date = target.exists() and expected is not None and _md5(target) == expected
    if force or not up_to_date:
        print(f"downloading {url}")
        last_modified = _download(url, target)
    else:
        print(f"up to date: {target.name}")
    actual = _md5(target)
    if expected is not None and actual != expected:
        target.unlink()
        raise OSError(f"checksum mismatch: {actual} != {expected}")
    return {
        "url": url,
        "md5": actual,
        "md5_verified": "yes" if expected else "no",
        "bytes": target.stat().st_size,
        "last_modified": last_modified,
    }


def fetch(
    paths: Paths, force: bool = False, urls: Sequence[str] = SOURCE_URLS
) -> dict[str, str | int | None]:
    """Download the source extract from the first mirror that works."""
    paths.downloads.mkdir(parents=True, exist_ok=True)
    failures = []
    for url in urls:
        try:
            source = _fetch_one(url, paths.source, force)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(f"  failed: {error}")
            failures.append(f"{url}: {error}")
            continue
        manifest = {
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source": source,
        }
        paths.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
        return source
    raise RuntimeError("every mirror failed:\n" + "\n".join(failures))
