"""Checks the real filtered extract. Skipped until `make extract` has been run."""

from collections import Counter

import osmium
import pytest
from osmium.filter import KeyFilter
from osmium.io import Reader
from osmium.osm import RELATION, WAY, Relation, Way, osm_entity_bits

from spirited.region import CLIP_BOX, DEFAULT_PATHS
from spirited.roadfilter import classify

pytestmark = [
    pytest.mark.extract,
    pytest.mark.skipif(
        not DEFAULT_PATHS.filtered.exists(),
        reason="no regional extract yet; run `make extract`",
    ),
]

# Roads that must survive the filter, by ref.
REQUIRED_REFS = {"M4", "A4", "A329", "A338", "A34", "B4000"}


@pytest.fixture(scope="module")
def highway_ways() -> list[dict[str, str]]:
    ways = []
    for obj in osmium.FileProcessor(str(DEFAULT_PATHS.filtered)).with_filter(KeyFilter("highway")):
        if isinstance(obj, Way):
            ways.append({tag.k: tag.v for tag in obj.tags})
    return ways


def test_extract_has_a_realistic_number_of_roads(highway_ways: list[dict[str, str]]) -> None:
    classes = Counter(tags["highway"] for tags in highway_ways)
    assert len(highway_ways) > 50_000
    assert classes["motorway"] > 100
    assert classes["unclassified"] > 1_000


def test_known_roads_are_present(highway_ways: list[dict[str, str]]) -> None:
    refs = set()
    for tags in highway_ways:
        refs.update(part.strip() for part in tags.get("ref", "").split(";"))
    assert refs >= REQUIRED_REFS


def test_every_remaining_highway_passes_the_filter(highway_ways: list[dict[str, str]]) -> None:
    failures = [tags for tags in highway_ways if not classify(tags).keep]
    assert failures == []


def test_header_bounds_match_the_clip_box() -> None:
    header = Reader(str(DEFAULT_PATHS.filtered), osm_entity_bits.NOTHING)
    box = header.header().box()
    header.close()
    assert box.bottom_left.lon == pytest.approx(CLIP_BOX.min_lon)
    assert box.top_right.lat == pytest.approx(CLIP_BOX.max_lat)


def test_england_boundary_is_complete() -> None:
    # Valhalla needs whole admin boundaries to know the UK drives on the left.
    members: list[int] = []
    for obj in osmium.FileProcessor(str(DEFAULT_PATHS.filtered), RELATION):
        if not isinstance(obj, Relation):
            continue
        tags = obj.tags
        if tags.get("boundary") == "administrative" and tags.get("name") == "England":
            members = [m.ref for m in obj.members if m.type == "w"]
    assert members, "England boundary relation missing"
    ways = {obj.id for obj in osmium.FileProcessor(str(DEFAULT_PATHS.filtered), WAY)}
    assert set(members) <= ways
