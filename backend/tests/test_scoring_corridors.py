import numpy as np

from spirited.scoring.corridors import WaySegment, build_corridors


def way(
    way_id: int, nodes: tuple[int, ...], key: str = "B4009", labelled: bool = True
) -> WaySegment:
    lonlat = np.array([[float(n), 0.0] for n in nodes])
    return WaySegment(way_id, nodes, lonlat, (key, "secondary", ""), labelled=labelled)


def degree(ways: list[WaySegment]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for w in ways:
        for node in set(w.node_ids):
            counts[node] = counts.get(node, 0) + 1
    return counts


def test_ways_of_one_road_join_whatever_their_direction() -> None:
    ways = [way(10, (1, 2, 3)), way(11, (5, 4, 3)), way(12, (5, 6))]
    [corridor] = build_corridors(ways, degree(ways))
    assert corridor.id == 10
    assert set(corridor.way_ids) == {10, 11, 12}
    assert corridor.node_ids in ((1, 2, 3, 4, 5, 6), (6, 5, 4, 3, 2, 1))
    assert len(corridor.lonlat) == 6


def test_a_ref_change_splits_the_road() -> None:
    ways = [way(10, (1, 2)), way(11, (2, 3), key="B4000")]
    corridors = build_corridors(ways, degree(ways))
    assert sorted(c.way_ids for c in corridors) == [(10,), (11,)]


def test_labelled_road_continues_through_a_crossroads() -> None:
    ways = [
        way(10, (1, 2)),
        way(11, (2, 3)),
        way(20, (7, 2), key="Side Lane"),
        way(21, (2, 8), key="Side Lane"),
    ]
    corridors = {c.key[0]: c for c in build_corridors(ways, degree(ways))}
    assert set(corridors["B4009"].way_ids) == {10, 11}
    assert set(corridors["Side Lane"].way_ids) == {20, 21}


def test_a_fork_of_the_same_road_does_not_join() -> None:
    ways = [way(10, (1, 2)), way(11, (2, 3)), way(12, (2, 4))]
    corridors = build_corridors(ways, degree(ways))
    assert len(corridors) == 3


def test_unlabelled_ways_join_only_where_nothing_else_meets() -> None:
    plain = [way(10, (1, 2), key="", labelled=False), way(11, (2, 3), key="", labelled=False)]
    assert len(build_corridors(plain, degree(plain))) == 1
    side = [*plain, way(30, (2, 9), key="Other Road")]
    assert len(build_corridors(side, degree(side))) == 3


def test_roundabouts_never_join() -> None:
    ring = WaySegment(40, (1, 2, 3, 1), np.zeros((4, 2)), ("A4", "primary", ""), roundabout=True)
    ways = [ring, way(10, (1, 5), key="A4")]
    assert len(build_corridors(ways, degree(ways))) == 2


def test_a_closed_loop_of_one_road_comes_back_as_one_corridor() -> None:
    ways = [way(10, (1, 2, 3)), way(11, (3, 4, 1))]
    [corridor] = build_corridors(ways, degree(ways))
    assert set(corridor.way_ids) == {10, 11}
