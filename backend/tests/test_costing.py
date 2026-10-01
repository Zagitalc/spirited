from spirited.routing.costing import AUTO_OPTIONS, costing_options


def test_profile_is_pinned() -> None:
    # Changing the safety-related options must be a deliberate edit to this test.
    assert AUTO_OPTIONS == {
        "use_tracks": 0.0,
        "exclude_unpaved": True,
        "use_living_streets": 0.0,
        "service_penalty": 300,
        "use_ferry": 0.0,
        "ignore_access": False,
        "use_highways": 0.5,
    }


def test_costing_options_returns_a_copy() -> None:
    options = costing_options()
    options["auto"]["use_tracks"] = 1.0
    assert AUTO_OPTIONS["use_tracks"] == 0.0
