from pathlib import Path

import osmium
from osmium.io import Reader
from osmium.osm import Node, Relation, Way, osm_entity_bits

from spirited.extract.roadfilter_pbf import filter_file

OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <bounds minlat="51.4" minlon="-1.0" maxlat="51.5" maxlon="-0.9"/>
  <node id="1" version="1" lat="51.45" lon="-0.97"/>
  <node id="2" version="1" lat="51.46" lon="-0.96"/>
  <node id="3" version="1" lat="51.47" lon="-0.95"/>
  <way id="10" version="1">
    <nd ref="1"/><nd ref="2"/>
    <tag k="highway" v="primary"/><tag k="ref" v="A4"/>
  </way>
  <way id="11" version="1">
    <nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="track"/><tag k="tracktype" v="grade4"/>
  </way>
  <way id="12" version="1">
    <nd ref="1"/><nd ref="3"/>
    <tag k="highway" v="residential"/><tag k="access" v="private"/>
    <tag k="name" v="Manor Drive"/>
  </way>
  <way id="13" version="1">
    <nd ref="1"/><nd ref="3"/>
    <tag k="boundary" v="administrative"/><tag k="admin_level" v="6"/>
  </way>
  <relation id="20" version="1">
    <member type="way" ref="13" role="outer"/>
    <tag k="boundary" v="administrative"/><tag k="type" v="boundary"/>
  </relation>
</osm>
"""


def _contents(path: Path) -> tuple[set[int], set[int], set[int]]:
    nodes, ways, relations = set(), set(), set()
    for obj in osmium.FileProcessor(str(path)):
        if isinstance(obj, Node):
            nodes.add(obj.id)
        elif isinstance(obj, Way):
            ways.add(obj.id)
        elif isinstance(obj, Relation):
            relations.add(obj.id)
    return nodes, ways, relations


def test_filter_drops_unsafe_highways_and_keeps_everything_else(tmp_path: Path) -> None:
    source = tmp_path / "sample.osm"
    source.write_text(OSM_XML)
    target = tmp_path / "filtered.osm.pbf"
    excluded_csv = tmp_path / "excluded.csv"

    result = filter_file(source, target, excluded_csv)

    nodes, ways, relations = _contents(target)
    assert ways == {10, 13}
    assert nodes == {1, 2, 3}
    assert relations == {20}
    assert result.kept == 1
    assert dict(result.excluded) == {"highway_class": 1, "access": 1}

    reader = Reader(str(target), osm_entity_bits.NOTHING)
    box = reader.header().box()
    reader.close()
    assert box.bottom_left.lon == -1.0
    assert box.top_right.lat == 51.5

    lines = excluded_csv.read_text().splitlines()
    assert lines[0] == "way_id,highway,reason,name,ref"
    assert sorted(line.split(",")[0] for line in lines[1:]) == ["11", "12"]
