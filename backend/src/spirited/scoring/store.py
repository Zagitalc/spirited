"""Read access to scores.sqlite, shared by the evaluation and (in Stage 3) loop scoring."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from spirited.scoring.components import Component

COMPONENT_COLUMNS = tuple(f"{name}_score" for name in Component)


class ScoreStore:
    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found: run `make scores` first")
        # Read only and used by one request at a time, but FastAPI may open it on one worker
        # thread and use or close it on another, which sqlite3 refuses by default.
        self._db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self._db.row_factory = sqlite3.Row

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ScoreStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def anchors(
        self, box: tuple[float, float, float, float], min_length_m: float
    ) -> list[sqlite3.Row]:
        """Points on recommendable corridors inside `box` (min lon, min lat, max lon,
        max lat), best-scored corridor first. `min_length_m` is the shortest corridor wanted."""
        min_lon, min_lat, max_lon, max_lat = box
        try:
            return self._db.execute(
                "SELECT a.corridor_id, a.lon, a.lat, c.label, c.highway, c.length_m, c.score "
                "FROM anchors a JOIN corridors c ON c.id = a.corridor_id "
                "WHERE c.length_m >= ? AND a.lat BETWEEN ? AND ? AND a.lon BETWEEN ? AND ? "
                "ORDER BY c.score DESC",
                (min_length_m, min_lat, max_lat, min_lon, max_lon),
            ).fetchall()
        except sqlite3.OperationalError as error:
            raise RuntimeError(
                "scores.sqlite has no anchor points: run `make scores` again"
            ) from error

    def corridors_for_ways(self, way_ids: Iterable[int]) -> dict[int, sqlite3.Row]:
        """The corridor row for each way id that has one, keyed by way id."""
        ids = sorted(set(way_ids))
        found: dict[int, sqlite3.Row] = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            marks = ", ".join("?" for _ in chunk)
            query = (
                "SELECT w.way_id AS way_id, c.* FROM corridor_ways w "
                f"JOIN corridors c ON c.id = w.corridor_id WHERE w.way_id IN ({marks})"
            )
            for row in self._db.execute(query, chunk):
                found[row["way_id"]] = row
        return found
