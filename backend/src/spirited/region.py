"""The area Spirited covers: Berkshire and the counties around it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The whole of England is downloaded (about 1.5 GB) and clipped locally to the region
# box. Mirrors are tried in order. On 2026-10-01 Geofabrik's England file redirected to
# a 404 and its dated files stalled, so the OpenStreetMap France mirror comes first.
SOURCE_NAME = "england"
SOURCE_URLS = (
    "https://download.openstreetmap.fr/extracts/europe/united_kingdom/england-latest.osm.pbf",
    "https://download.geofabrik.de/europe/united-kingdom/england-latest.osm.pbf",
)


@dataclass(frozen=True)
class BBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def as_osmium_arg(self) -> str:
        return f"{self.min_lon},{self.min_lat},{self.max_lon},{self.max_lat}"

    def contains(self, lon: float, lat: float) -> bool:
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat


# Reaches Swindon, Oxford, Basingstoke and Guildford, and takes the western fringe of
# London for loops from Windsor or Slough, but stops short of central London.
# Checked against real loop radii in Stage 3 (see docs/decisions.md).
CLIP_BOX = BBox(min_lon=-2.2, min_lat=51.05, max_lon=-0.30, max_lat=51.90)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "osm"


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def downloads(self) -> Path:
        return self.root / "downloads"

    @property
    def source(self) -> Path:
        return self.downloads / f"{SOURCE_NAME}-latest.osm.pbf"

    @property
    def clipped(self) -> Path:
        return self.root / "region.osm.pbf"

    @property
    def filtered(self) -> Path:
        return self.root / "region-filtered.osm.pbf"

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def report(self) -> Path:
        return self.root / "filter-report.json"

    @property
    def excluded_csv(self) -> Path:
        return self.root / "excluded-ways.csv"


DEFAULT_PATHS = Paths(DATA_DIR)
