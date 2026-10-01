# Decisions

Newest first. Each entry says what was decided, why, and what would make us
revisit it.

## 2026-10-01: Patches instead of commits from Claude

**Decision.** Claude prepares each stage as a patch with the git commands to apply
it. The project owner commits and pushes.

**Why.** The owner wants to control what lands in the repository.

## 2026-10-01: Region and clip box

**Decision.** Download an England extract and clip it with osmium to the
box 2.2°W to 0.30°W, 51.05°N to 51.90°N using the `complete_ways` strategy.

The first version downloaded seven county extracts and merged them, but on
2026-10-01 those addresses returned 404, so the pipeline now takes the whole of
England. It is a larger download (about 1.5 GB) but has no merge step and does not
depend on Geofabrik's county list.

Later the same day, Geofabrik's England file also redirected to a 404, and its dated
files accepted connections but sent no data. The pipeline now tries the OpenStreetMap
France mirror first and Geofabrik second, treats 60 seconds without data as a failure,
and accepts `--url` for any other source.

**Why.** A 90-minute loop from the edge of Berkshire can travel 30 km or more in any
direction. The box reaches Swindon, Oxford, Basingstoke and Guildford, and includes
the western fringe of London for loops from Windsor or Slough, but not central London.

**Revisit when** Stage 3 shows loops running into the edge of the box.

## 2026-10-01: Filter the extract before routing

**Decision.** The road safety rule is applied in Python to the OSM extract before
Valhalla builds its graph. Ways that fail are removed, and only highway ways are
touched: nodes, relations and other ways (such as administrative boundaries, which
Valhalla needs for driving side) are copied unchanged. Valhalla's own costing options
(`exclude_unpaved`, `use_tracks`) stay on as a second line of defence.

**Why.** Valhalla's costing can exclude unpaved roads and tracks, but it cannot treat
a missing surface tag on a minor road as suspect, and its handling of private access
is not something we want to depend on. Filtering first means the router cannot use
an excluded road under any costing, and the rule is plain Python with unit tests.
It also keeps the safety rule independent of the router if we ever change it.

The rules are in `backend/src/spirited/roadfilter.py`:

- Kept classes: motorway, trunk, primary, secondary, tertiary, unclassified,
  residential and their links. Residential roads stay routable so that loops can
  leave towns, but scoring will never reward them. Living streets, service roads,
  tracks and everything else are dropped.
- Access: the most specific of `motorcar`, `motor_vehicle`, `vehicle` and `access`
  decides. Only `yes`, `permissive`, `designated`, `destination` and `customers`
  allow a car; anything else, including unrecognised values, excludes the road.
- Surface: a surface tag must be a paved value. `tracktype` other than `grade1`,
  smoothness of `bad` or worse, fords, and UK byway or bridleway designations exclude
  the road.
- Missing surface: accepted on every kept class except `unclassified`, where a `name`
  or `ref` is required as evidence of a public road.

**Cost.** Some legitimate but under-tagged country lanes are lost. The exclusion
report counts them.

## 2026-10-01: Stack

**Decision.** Valhalla in Docker for routing and elevation; a Python 3.12 service
(FastAPI, pyosmium, Shapely, NumPy) for scoring and loop generation, storing
precomputed segment scores in SQLite; a native Android client in Kotlin with Jetpack
Compose and MapLibre Native.

**Why Valhalla.** It takes costing options per request, has elevation built in,
offers isochrones (useful for placing loop waypoints by time rather than straight-line
distance), and `trace_attributes` returns the OSM way id of each edge, so scoring can
live entirely in Python. GraphHopper was the serious alternative: its custom models
express road rules well, but it adds a JVM service and makes per-edge OSM attributes
harder to get back. OSRM was rejected because its profiles are fixed at build time
and it has no elevation.

**Why SQLite rather than PostGIS.** The region is small, the scores are built
offline, and a single file is much simpler to host.

**Tooling.** uv, ruff, pyright and pytest for Python. Gradle with a version catalogue
and Spotless with ktlint for Android. GitHub Actions runs both on every push.
