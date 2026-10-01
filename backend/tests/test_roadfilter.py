import pytest

from spirited.roadfilter import Reason, classify


@pytest.mark.parametrize(
    "tags",
    [
        {"highway": "primary", "ref": "A4"},
        {"highway": "motorway", "ref": "M4"},
        {"highway": "secondary_link"},
        {"highway": "tertiary", "surface": "asphalt"},
        {"highway": "residential"},
        {"highway": "unclassified", "surface": "asphalt"},
        {"highway": "unclassified", "name": "Hollow Lane"},
        {"highway": "unclassified", "ref": "C123"},
        {"highway": "tertiary", "access": "destination"},
        {"highway": "primary", "access": "no", "motor_vehicle": "yes"},
        {"highway": "primary", "motor_vehicle": "no", "motorcar": "yes"},
        {"highway": "tertiary", "tracktype": "grade1"},
        {"highway": "secondary", "smoothness": "intermediate"},
        {"highway": "unclassified", "name": "Mill Lane", "ford": "no"},
    ],
)
def test_keeps_public_paved_roads(tags: dict[str, str]) -> None:
    decision = classify(tags)
    assert decision.keep, tags
    assert decision.reason is Reason.KEPT


@pytest.mark.parametrize(
    ("tags", "reason"),
    [
        ({"building": "yes"}, Reason.NOT_A_ROAD),
        ({"highway": "track"}, Reason.HIGHWAY_CLASS),
        ({"highway": "service"}, Reason.HIGHWAY_CLASS),
        ({"highway": "living_street"}, Reason.HIGHWAY_CLASS),
        ({"highway": "footway"}, Reason.HIGHWAY_CLASS),
        ({"highway": "bridleway"}, Reason.HIGHWAY_CLASS),
        ({"highway": "byway"}, Reason.HIGHWAY_CLASS),
        ({"highway": "construction"}, Reason.HIGHWAY_CLASS),
        ({"highway": "road"}, Reason.HIGHWAY_CLASS),
        ({"highway": "residential", "access": "private"}, Reason.ACCESS),
        ({"highway": "unclassified", "access": "agricultural", "name": "X"}, Reason.ACCESS),
        ({"highway": "tertiary", "motor_vehicle": "no"}, Reason.ACCESS),
        ({"highway": "tertiary", "motor_vehicle": "forestry"}, Reason.ACCESS),
        ({"highway": "tertiary", "access": "permit"}, Reason.ACCESS),
        ({"highway": "tertiary", "access": "unknown"}, Reason.ACCESS),
        ({"highway": "tertiary", "motor_vehicle": "destination;no"}, Reason.ACCESS),
        ({"highway": "primary", "motor_vehicle": "yes", "motorcar": "no"}, Reason.ACCESS),
        (
            {"highway": "unclassified", "designation": "byway_open_to_all_traffic", "name": "X"},
            Reason.BYWAY,
        ),
        ({"highway": "unclassified", "ford": "yes", "name": "Ford Lane"}, Reason.FORD),
        ({"highway": "unclassified", "tracktype": "grade3", "name": "X"}, Reason.TRACKTYPE),
        ({"highway": "tertiary", "tracktype": "grade2"}, Reason.TRACKTYPE),
        ({"highway": "unclassified", "smoothness": "very_bad", "name": "X"}, Reason.SMOOTHNESS),
        ({"highway": "tertiary", "surface": "gravel"}, Reason.UNPAVED_SURFACE),
        ({"highway": "unclassified", "surface": "unpaved", "name": "X"}, Reason.UNPAVED_SURFACE),
        ({"highway": "residential", "surface": "dirt"}, Reason.UNPAVED_SURFACE),
        ({"highway": "secondary", "surface": "compacted"}, Reason.UNPAVED_SURFACE),
        ({"highway": "unclassified"}, Reason.UNEVIDENCED_UNCLASSIFIED),
        ({"highway": "unclassified", "name": ""}, Reason.UNEVIDENCED_UNCLASSIFIED),
    ],
)
def test_excludes_unsafe_or_unevidenced_roads(tags: dict[str, str], reason: Reason) -> None:
    decision = classify(tags)
    assert not decision.keep, tags
    assert decision.reason is reason


def test_paved_surface_overrides_missing_name_on_unclassified() -> None:
    assert classify({"highway": "unclassified", "surface": "asphalt"}).keep


def test_unclassified_needs_surface_or_name_or_ref() -> None:
    assert not classify({"highway": "unclassified", "maxspeed": "60 mph"}).keep
