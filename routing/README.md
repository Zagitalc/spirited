# Routing

Valhalla runs here in Docker. Its only input is
`backend/data/osm/region-filtered.osm.pbf`, the extract that has already been
through the road safety filter, so the router cannot use a road the filter removed
(see `docs/decisions.md`).

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

After re-running the extract pipeline, copy the new file in and rebuild:

```sh
cp backend/data/osm/region-filtered.osm.pbf routing/custom_files/
cd routing && FORCE_REBUILD=True docker compose up -d --force-recreate
```

## Apple Silicon

If `docker compose up` warns that the image's platform (`linux/amd64`) does not
match the host, the image has no Apple Silicon build and Docker is emulating it.
That works, but the first build is slower. Nothing needs changing.

## Elevation

`build_elevation=True` makes Valhalla download terrain tiles covering the routing
graph from the public Terrain Tiles dataset on AWS. See `docs/attribution.md`.
