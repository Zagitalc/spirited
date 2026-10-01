# Decisions

Newest first. Each entry says what was decided, why, and what would make us
revisit it.

## 2026-10-01: A generated UK boundary for Valhalla

**Decision.** The extract pipeline writes `uk-admin.osm.pbf`: one administrative
boundary, tagged as the United Kingdom (`ISO3166-1=GB`, `admin_level=2`), drawn as
a rectangle slightly larger than the clip box. Valhalla is built from it together
with the filtered extract.

**Why.** Valhalla needs a closed country boundary to know that traffic drives on
the left, which affects turn costs. Clipping cuts the real England and UK boundary
relations, so the first build reported "Inserted 0 admin areas". Keeping the
relations whole with osmium's `smart` strategy did not help either, because the
England extract we download does not contain every member of those relations. A
generated boundary is small, does not depend on the extract, and was checked with
`valhalla_build_admins` (Valhalla 3.9), which recorded `drive_on_right = 0` for it.

**Cost.** It is not the real boundary, so Valhalla will treat anything inside the
rectangle as the UK. Every road in the clip box is in England, so this changes
nothing in practice; it would need replacing if the region ever reached Wales or
the coast.

## 2026-10-01: Routing with Valhalla in Docker

**Decision.** Run the official `ghcr.io/valhalla/valhalla-scripted` image, built
only from `region-filtered.osm.pbf` with administrative areas, time zones and
elevation. The backend talks to it through a small client in `spirited.routing`
and sends the same car costing profile with every request:

| Option | Value | Why |
| --- | --- | --- |
| `use_tracks` | 0 | Never prefer tracks, should one slip through the filter |
| `exclude_unpaved` | true | Refuse unpaved edges outright |
| `use_living_streets` | 0 | Avoid living streets |
| `service_penalty` | 300 s | Guards against mistagged service roads |
| `use_ferry` | 0 | No ferries in a driving loop |
| `ignore_access` | false | Respect every access restriction |
| `use_highways` | 0.5 | Neutral for now; Stage 3 will lower it |

The profile is pinned by a unit test. Routes are checked against the roads the
filter removed by sending each leg back through `trace_attributes` with
`shape_match: edge_walk`, which returns the OSM way id of every edge used.

**Why.** Keeping the profile in Python rather than in Valhalla's server config means
every request states exactly what it asked for. The client was checked against
Valhalla 3.9 (through the `pyvalhalla` package) on a small synthetic network,
which confirmed the request and response formats; the real region has to be
checked on a machine that can download the map data.

**Revisit when** loop generation needs options the profile does not cover.

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
