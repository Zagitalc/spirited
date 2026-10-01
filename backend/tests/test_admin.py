from pathlib import Path

import osmium
from osmium.osm import Node, Relation, Way

from spirited.extract.admin import boundary_corners, write_admin_boundary
from spirited.region import CLIP_BOX


def test_boundary_surrounds_the_clip_box() -> None:
    corners = boundary_corners()
    lons = [lon for lon, _ in corners]
    lats = [lat for _, lat in corners]
    assert min(lons) < CLIP_BOX.min_lon and max(lons) > CLIP_BOX.max_lon
    assert min(lats) < CLIP_BOX.min_lat and max(lats) > CLIP_BOX.max_lat


def test_writes_a_closed_uk_boundary(tmp_path: Path) -> None:
    path = tmp_path / "uk-admin.osm.pbf"
    write_admin_boundary(path)

    nodes: dict[int, tuple[float, float]] = {}
    ways: dict[int, list[int]] = {}
    relations = []
    for obj in osmium.FileProcessor(str(path)):
        if isinstance(obj, Node):
            nodes[obj.id] = (obj.location.lon, obj.location.lat)
        elif isinstance(obj, Way):
            ways[obj.id] = [n.ref for n in obj.nodes]
        elif isinstance(obj, Relation):
            relations.append((dict(obj.tags), [(m.type, m.ref, m.role) for m in obj.members]))

    assert len(relations) == 1
    tags, members = relations[0]
    assert tags["ISO3166-1"] == "GB"
    assert tags["admin_level"] == "2"
    assert tags["boundary"] == "administrative"
    (member_type, way_id, role) = members[0]
    assert (member_type, role) == ("w", "outer")
    ring = ways[way_id]
    assert ring[0] == ring[-1], "boundary must be a closed ring"
    assert {nodes[n] for n in ring} == {
        (round(lon, 7), round(lat, 7)) for lon, lat in boundary_corners()
    }
