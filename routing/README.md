# Routing

Valhalla runs here in Docker. Its only input is
`backend/data/osm/region-filtered.osm.pbf`: the extract after the road safety
filter, so the router cannot use a road the filter removed, plus a generated UK
boundary that tells Valhalla traffic drives on the left (see `docs/decisions.md`).
Put nothing else in `custom_files/`: Valhalla builds from every `.pbf` it finds
there and aborts if they are not one sorted file. The build log should say
"Inserted 1 admin areas".

## Running it

From the repository root, after `make extract`:

```sh
make routing            # copies the filtered extract in, builds tiles, serves on :8002
```

or by hand:

```sh
cp backend/data/osm/region-filtered.osm.pbf routing/custom_files/
cd routing
docker compose up -d
docker compose logs -f valhalla     # wait for the build to finish
curl http://localhost:8002/status
```

The first start builds routing tiles, administrative areas, time zones and
elevation for the region. Everything it produces stays in `routing/custom_files/`,
which is not committed. Later starts reuse the tiles and take seconds.

After re-running the extract pipeline, rebuild from the repository root:

```sh
make routing-rebuild
```

That copies the new file in, deletes the old tiles and boundary database, and
restarts Valhalla with `FORCE_REBUILD=True`. The deletion matters: a forced
rebuild redoes the tiles but keeps an existing `admins.sqlite`, so a
boundary database built from an older extract would survive it. Elevation and
time-zone data are kept because they do not depend on the extract.

To check the boundary database afterwards:

```sh
sqlite3 routing/custom_files/admins.sqlite "select name, iso_code, drive_on_right from admins;"
# United Kingdom|GB|0
```

## Apple Silicon

If `docker compose up` warns that the image's platform (`linux/amd64`) does not
match the host, the image has no Apple Silicon build and Docker is emulating it.
That works, but the first build is slower. Nothing needs changing.

## Elevation

`build_elevation=True` makes Valhalla download terrain tiles covering the routing
graph from the public Terrain Tiles dataset on AWS. See `docs/attribution.md`.
