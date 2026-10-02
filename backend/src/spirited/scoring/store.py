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
        self._db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self._db.row_factory = sqlite3.Row

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ScoreStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

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
