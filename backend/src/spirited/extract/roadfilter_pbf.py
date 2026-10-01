"""Apply the road safety filter to an OSM file.

Only highway ways that fail the filter are removed. Nodes, relations and every
non-highway way are copied unchanged, because Valhalla still needs administrative
boundaries (for driving side and country rules) and other context from the file.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import osmium
from osmium.osm import Way

from spirited.roadfilter import Reason, classify


@dataclass
class FilterResult:
    kept: int = 0
    excluded: Counter[str] = field(default_factory=Counter)

    @property
    def excluded_total(self) -> int:
        return sum(self.excluded.values())

    def as_report(self) -> dict[str, object]:
        return {
            "highway_ways_kept": self.kept,
            "highway_ways_excluded": self.excluded_total,
            "excluded_by_reason": dict(self.excluded.most_common()),
        }


def filter_file(source: Path, target: Path, excluded_csv: Path | None = None) -> FilterResult:
    result = FilterResult()
    processor = osmium.FileProcessor(str(source))
    # Carry the source header across so the clip bounds survive into the output.
    writer = osmium.SimpleWriter(str(target), header=processor.header, overwrite=True)
    csv_handle = excluded_csv.open("w", newline="") if excluded_csv else None
    rows = csv.writer(csv_handle) if csv_handle else None
    if rows:
        rows.writerow(["way_id", "highway", "reason", "name", "ref"])
    try:
        for obj in processor:
            if isinstance(obj, Way) and "highway" in obj.tags:
                tags = {tag.k: tag.v for tag in obj.tags}
                decision = classify(tags)
                if not decision.keep:
                    result.excluded[decision.reason.value] += 1
                    if rows:
                        rows.writerow(
                            [
                                obj.id,
                                tags["highway"],
                                decision.reason.value,
                                tags.get("name", ""),
                                tags.get("ref", ""),
                            ]
                        )
                    continue
                result.kept += 1
            writer.add(obj)
    finally:
        writer.close()
        if csv_handle:
            csv_handle.close()
    return result


def write_report(result: FilterResult, path: Path) -> None:
    path.write_text(json.dumps(result.as_report(), indent=2) + "\n")


__all__ = ["FilterResult", "Reason", "filter_file", "write_report"]
