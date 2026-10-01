import urllib.error
from pathlib import Path

import pytest

from spirited.extract import fetch as fetch_module
from spirited.region import Paths


def test_falls_back_to_the_next_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch_one(url: str, target: Path, force: bool) -> dict[str, str | int | None]:
        calls.append(url)
        if "first" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        target.write_bytes(b"pbf")
        return {"url": url, "md5": "x", "md5_verified": "no", "bytes": 3, "last_modified": None}

    monkeypatch.setattr(fetch_module, "_fetch_one", fake_fetch_one)
    paths = Paths(tmp_path)

    source = fetch_module.fetch(paths, urls=["https://first/a.pbf", "https://second/a.pbf"])

    assert calls == ["https://first/a.pbf", "https://second/a.pbf"]
    assert source["url"] == "https://second/a.pbf"
    assert paths.manifest.exists()


def test_reports_every_failure_when_all_mirrors_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_stalls(url: str, target: Path, force: bool) -> dict[str, str | int | None]:
        raise TimeoutError("timed out")

    monkeypatch.setattr(fetch_module, "_fetch_one", always_stalls)

    with pytest.raises(RuntimeError, match="every mirror failed"):
        fetch_module.fetch(Paths(tmp_path), urls=["https://a/x.pbf", "https://b/x.pbf"])
