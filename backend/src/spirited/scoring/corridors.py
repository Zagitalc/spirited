"""Join OSM ways into corridors: runs of road a driver would think of as one stretch.

OSM splits a road wherever a tag changes, at bridges, and wherever an editor happened
to stop, so a single bend can be cut across two ways. Ways are joined end to end when
they carry the same ref (or the same name, for roads without a ref), the same highway
class and the same eligibility, and when exactly two such ways meet at the node.
Unlabelled ways join only where no other road meets them. A roundabout never joins.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from spirited.scoring.geometry import Coords


@dataclass(frozen=True)
class WaySegment:
    way_id: int
    node_ids: tuple[int, ...]
    lonlat: Coords
    # Ways join only when their keys are equal.
    key: tuple[str, ...]
    # Unlabelled ways and roundabouts are joined more cautiously, see the module doc.
    labelled: bool = True
    roundabout: bool = False


@dataclass(frozen=True)
class Corridor:
    id: int
    way_ids: tuple[int, ...]
    node_ids: tuple[int, ...]
    lonlat: Coords
    key: tuple[str, ...]


def build_corridors(ways: Sequence[WaySegment], node_degree: Mapping[int, int]) -> list[Corridor]:
    """Chain ways into corridors. `node_degree` counts the road ways touching each node."""
    ends: defaultdict[tuple[tuple[str, ...], int], list[int]] = defaultdict(list)
    for index, way in enumerate(ways):
        if way.roundabout or len(way.node_ids) < 2:
            continue
        ends[(way.key, way.node_ids[0])].append(index)
        if way.node_ids[-1] != way.node_ids[0]:
            ends[(way.key, way.node_ids[-1])].append(index)

    def partner(index: int, node: int) -> int | None:
        way = ways[index]
        candidates = ends.get((way.key, node), [])
        if len(candidates) != 2 or candidates[0] == candidates[1]:
            return None
        if not way.labelled and node_degree.get(node, 0) != 2:
            return None
        other = candidates[1] if candidates[0] == index else candidates[0]
        return other

    used = [False] * len(ways)
    corridors: list[Corridor] = []

    def walk(start: int, start_node: int) -> list[tuple[int, bool]]:
        """Ways from `start`, leaving it through the end opposite `start_node`."""
        chain: list[tuple[int, bool]] = []
        index, entry = start, start_node
        while True:
            way = ways[index]
            forward = way.node_ids[0] == entry
            chain.append((index, forward))
            used[index] = True
            exit_node = way.node_ids[-1] if forward else way.node_ids[0]
            nxt = partner(index, exit_node)
            if nxt is None or used[nxt]:
                return chain
            index, entry = nxt, exit_node

    for index, way in enumerate(ways):
        if used[index]:
            continue
        if way.roundabout or len(way.node_ids) < 2:
            used[index] = True
            corridors.append(_corridor([(index, True)], ways))
            continue
        # Find one end of the run this way belongs to, then walk the whole run.
        entry_node = way.node_ids[0]
        current = index
        seen = {index}
        while True:
            back = partner(current, entry_node)
            if back is None or back in seen:
                break
            seen.add(back)
            other = ways[back]
            entry_node = (
                other.node_ids[-1] if other.node_ids[0] == entry_node else other.node_ids[0]
            )
            current = back
        corridors.append(_corridor(walk(current, entry_node), ways))
    return corridors


def _corridor(chain: Iterable[tuple[int, bool]], ways: Sequence[WaySegment]) -> Corridor:
    way_ids: list[int] = []
    node_ids: list[int] = []
    parts: list[Coords] = []
    key: tuple[str, ...] = ()
    for index, forward in chain:
        way = ways[index]
        key = way.key
        nodes = way.node_ids if forward else way.node_ids[::-1]
        coords = way.lonlat if forward else way.lonlat[::-1]
        if node_ids:
            nodes, coords = nodes[1:], coords[1:]
        way_ids.append(way.way_id)
        node_ids.extend(nodes)
        parts.append(coords)
    return Corridor(
        id=min(way_ids),
        way_ids=tuple(way_ids),
        node_ids=tuple(node_ids),
        lonlat=np.concatenate(parts) if parts else np.zeros((0, 2)),
        key=key,
    )
