import pytest

from spirited.scoring.speed import SpeedSource, parse_maxspeed, speed_limit


@pytest.mark.parametrize(
    ("value", "mph"),
    [
        ("40 mph", 40),
        ("40mph", 40),
        ("80", 80 / 1.609344),  # a bare number is km/h
        ("30 mph;20 mph", 20),  # a list takes the lowest
        ("national", None),
        ("signals", None),
        ("40 mph;fast", None),
        ("", None),
    ],
)
def test_parse_maxspeed(value: str, mph: float | None) -> None:
    assert parse_maxspeed(value) == (pytest.approx(mph) if mph is not None else None)


def test_tagged_limit_wins_over_everything_else() -> None:
    limit = speed_limit({"highway": "secondary", "maxspeed": "50 mph", "lit": "yes"}, True)
    assert (limit.mph, limit.source, limit.confidence) == (50, SpeedSource.TAGGED, 1.0)


@pytest.mark.parametrize(
    ("tags", "mph"),
    [
        ({"highway": "secondary", "maxspeed": "national"}, 60),
        ({"highway": "trunk", "maxspeed": "national", "dual_carriageway": "yes"}, 70),
        ({"highway": "tertiary", "maxspeed:type": "GB:nsl_single"}, 60),
        ({"highway": "primary", "maxspeed:type": "GB:nsl_dual"}, 70),
        ({"highway": "unclassified", "source:maxspeed": "GB:zone20"}, 20),
        ({"highway": "motorway"}, 70),
    ],
)
def test_national_limit_tags(tags: dict[str, str], mph: float) -> None:
    limit = speed_limit(tags, in_settlement=False)
    assert limit.mph == mph
    assert limit.source is SpeedSource.NATIONAL_TAG


def test_street_lighting_means_30_except_on_trunk_roads() -> None:
    lit = speed_limit({"highway": "secondary", "lit": "yes"}, in_settlement=False)
    assert (lit.mph, lit.source) == (30, SpeedSource.LIT)
    trunk = speed_limit({"highway": "trunk", "lit": "yes"}, in_settlement=False)
    assert trunk.source is SpeedSource.ASSUMED


def test_untagged_road_in_a_village_is_30() -> None:
    limit = speed_limit({"highway": "tertiary"}, in_settlement=True)
    assert (limit.mph, limit.source) == (30, SpeedSource.SETTLEMENT)


def test_untagged_rural_road_is_assumed_national_with_low_confidence() -> None:
    limit = speed_limit({"highway": "tertiary"}, in_settlement=False)
    assert (limit.mph, limit.source) == (60, SpeedSource.ASSUMED)
    assert limit.confidence < 0.5
