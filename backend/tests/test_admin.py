import shutil
import subprocess
from pathlib import Path

import osmium
import pytest
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


def test_ids_sort_after_real_osm_objects() -> None:
    from spirited.extract.admin import ID_BASE, RELATION_ID, WAY_ID

    assert ID_BASE > 10**11
    assert WAY_ID > ID_BASE and RELATION_ID > ID_BASE


@pytest.mark.skipif(shutil.which("osmium") is None, reason="needs osmium-tool")
def test_merges_into_the_filtered_extract(tmp_path: Path) -> None:
    from spirited.extract.admin import add_admin_boundary
    from spirited.region import Paths

    paths = Paths(tmp_path)
    source = tmp_path / "roads.osm"
    source.write_text(
        "<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6'>"
        "<node id='1' version='1' lat='51.45' lon='-0.97'/>"
        "<node id='2' version='1' lat='51.46' lon='-0.96'/>"
        "<way id='10' version='1'><nd ref='1'/><nd ref='2'/>"
        "<tag k='highway' v='primary'/></way></osm>"
    )
    osmium.SimpleWriter(str(paths.filtered), overwrite=True).close()
    subprocess.run(["osmium", "cat", str(source), "-o", str(paths.filtered), "-O"], check=True)

    add_admin_boundary(paths)
    add_admin_boundary(paths)  # running it twice must not duplicate anything

    ids: list[tuple[str, int]] = []
    for obj in osmium.FileProcessor(str(paths.filtered)):
        kind = "n" if isinstance(obj, Node) else "w" if isinstance(obj, Way) else "r"
        ids.append((kind, obj.id))
    order = {"n": 0, "w": 1, "r": 2}
    assert ids == sorted(ids, key=lambda item: (order[item[0]], item[1])), "must stay sorted"
    assert len(ids) == len(set(ids))
    assert ("w", 10) in ids
    assert sum(1 for kind, _ in ids if kind == "r") == 1
