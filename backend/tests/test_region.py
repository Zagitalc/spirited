from spirited.region import CLIP_BOX, SOURCE_URLS

# (name, lon, lat) of places the region must cover.
MUST_COVER = [
    ("Reading", -0.97, 51.45),
    ("Newbury", -1.32, 51.40),
    ("Windsor", -0.61, 51.48),
    ("Lambourn", -1.53, 51.51),
    ("Henley-on-Thames", -0.90, 51.54),
    ("Oxford", -1.26, 51.75),
    ("Basingstoke", -1.09, 51.27),
    ("Marlborough", -1.73, 51.42),
    ("Guildford", -0.57, 51.24),
]


def test_clip_box_covers_berkshire_and_its_neighbours() -> None:
    for name, lon, lat in MUST_COVER:
        assert CLIP_BOX.contains(lon, lat), name


def test_clip_box_stops_short_of_central_london() -> None:
    assert not CLIP_BOX.contains(-0.13, 51.51)


def test_every_mirror_serves_the_england_extract() -> None:
    assert len(SOURCE_URLS) >= 2
    for url in SOURCE_URLS:
        assert url.startswith("https://")
        assert url.endswith("england-latest.osm.pbf")
