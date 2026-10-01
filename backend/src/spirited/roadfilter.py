"""Road safety filter: decides which OSM highways an ordinary car may be routed on.

The rule is to exclude by default and include on evidence. A way is kept only when
its highway class, access tags and surface tags all point to a public, paved road.
Everything else is dropped from the extract before Valhalla builds its graph, so the
router cannot use it whatever its costing options say.

The function is pure: it takes a tag mapping and returns a decision with a reason,
which keeps the rules easy to test and the exclusion report easy to read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Reason(StrEnum):
    KEPT = "kept"
    NOT_A_ROAD = "not_a_road"
    HIGHWAY_CLASS = "highway_class"
    ACCESS = "access"
    UNPAVED_SURFACE = "unpaved_surface"
    TRACKTYPE = "tracktype"
    SMOOTHNESS = "smoothness"
    FORD = "ford"
    BYWAY = "byway"
    UNEVIDENCED_UNCLASSIFIED = "unevidenced_unclassified"


@dataclass(frozen=True)
class Decision:
    keep: bool
    reason: Reason


# Classes an ordinary car may use. Residential roads stay routable so that loops can
# start and finish in a town, but scoring (Stage 2) never rewards them.
ROUTABLE_CLASSES = frozenset(
    {
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "residential",
        "motorway_link",
        "trunk_link",
        "primary_link",
        "secondary_link",
        "tertiary_link",
    }
)

# Classes where a missing surface tag is normal: these are almost always sealed.
SURFACE_PRESUMED_PAVED = ROUTABLE_CLASSES - {"unclassified"}

PAVED_SURFACES = frozenset(
    {
        "paved",
        "asphalt",
        "chipseal",
        "concrete",
        "concrete:plates",
        "concrete:lanes",
        "paving_stones",
        "sett",
    }
)

BAD_SMOOTHNESS = frozenset({"bad", "very_bad", "horrible", "very_horrible", "impassable"})

# Access values that positively allow a private car. Anything else, including
# values we do not recognise, counts as a restriction.
ALLOWED_ACCESS = frozenset({"yes", "permissive", "designated", "destination", "customers"})

# Most specific first: the first of these keys present on the way decides access.
ACCESS_KEYS = ("motorcar", "motor_vehicle", "vehicle", "access")

# UK rights-of-way designations that are not ordinary roads even when tagged as one.
BYWAY_DESIGNATIONS = frozenset(
    {"byway_open_to_all_traffic", "restricted_byway", "public_bridleway", "public_footpath"}
)


def _access_allows_car(tags: Mapping[str, str]) -> bool:
    for key in ACCESS_KEYS:
        value = tags.get(key)
        if value is not None:
            # Values can be lists such as "no;destination". Every part must allow it.
            parts = [part.strip() for part in value.split(";")]
            return all(part in ALLOWED_ACCESS for part in parts)
    return True


def classify(tags: Mapping[str, str]) -> Decision:
    """Decide whether a way with these tags may appear in the routing graph."""
    highway = tags.get("highway")
    if highway is None:
        return Decision(False, Reason.NOT_A_ROAD)
    if highway not in ROUTABLE_CLASSES:
        return Decision(False, Reason.HIGHWAY_CLASS)
    if not _access_allows_car(tags):
        return Decision(False, Reason.ACCESS)
    if tags.get("designation") in BYWAY_DESIGNATIONS:
        return Decision(False, Reason.BYWAY)
    if tags.get("ford", "no") != "no":
        return Decision(False, Reason.FORD)

    tracktype = tags.get("tracktype")
    if tracktype is not None and tracktype != "grade1":
        return Decision(False, Reason.TRACKTYPE)
    if tags.get("smoothness") in BAD_SMOOTHNESS:
        return Decision(False, Reason.SMOOTHNESS)

    surface = tags.get("surface")
    if surface is not None:
        if surface not in PAVED_SURFACES:
            return Decision(False, Reason.UNPAVED_SURFACE)
        return Decision(True, Reason.KEPT)

    if highway in SURFACE_PRESUMED_PAVED:
        return Decision(True, Reason.KEPT)
    # An unclassified road with no surface tag is suspect. A name or a ref is the
    # evidence that it is a public road rather than a farm or estate lane.
    if tags.get("name") or tags.get("ref"):
        return Decision(True, Reason.KEPT)
    return Decision(False, Reason.UNEVIDENCED_UNCLASSIFIED)
