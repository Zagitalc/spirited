# Decisions

Newest first. Each entry says what was decided, why, and what would make us
revisit it.

## 2026-10-02: Unclassified roads without a surface tag are never recommended

**Decision.** In a corridor's confidence, the surface factor for an unclassified way
with no paved `surface` tag is 0.55 instead of 0.9. That alone puts a corridor made of
such ways below the 0.6 cut-off, so it is still scored and routable but never
recommended for itself. Other classes without a surface tag keep the 0.9 factor.

**Why.** The project's safety rule says missing surface data on minor roads is suspect
and low-confidence segments are excluded from recommendations. The first build applied
only the 0.9 factor, so no corridor fell below the cut-off and the rule had no effect:
Mill Lane, tagged with nothing but `highway=unclassified` and a name, scored in the
90s. The Stage 0 filter lets such roads into the routing graph when they have a name;
this keeps them out of what Spirited recommends.

**Cost.** Good lanes that simply lack a surface tag drop out of recommendations. The
reference roads will show how many; adding `surface=asphalt` in OSM brings them back.

## 2026-10-02: Narrow lanes score lower

**Decision.** A corridor's score is multiplied by `1 - 0.5 × narrowness`, where
narrowness is the length-weighted share of road that is narrow. A way counts as
narrow (1) when it is two-way and tagged `lanes=1` or a `width`/`est_width` under
5 m, and a whole corridor counts as narrow when it has a `highway=passing_place` node.
An unclassified way with no lanes or width tag counts as possibly narrow (0.5), so its
score drops by a quarter. A tag showing two lanes or a width of 5 m or more clears it.

**Why.** In the first real build, a road LonZac knows as twisty and semi single-track
ranked near the top, because the score rewarded its bends and knew nothing about its
width. Its OSM tags were only `highway=unclassified`, `oneway=no` and
`surface=asphalt`, which is typical: most lanes have no width tag, so tags alone would
miss them. In England most single-track roads are unclassified, while B roads are
nearly always two lanes, so the road class is the best remaining signal.

**Cost.** Good, wide unclassified roads without a lanes tag are marked down too. The
penalty is not part of the confidence value; a tag showing two lanes removes it.

## 2026-10-01: Road scoring (Stage 2)

**Decision.** Roads are scored offline in Python from `region-filtered.osm.pbf` and
written to `backend/data/scores.sqlite`, one row per corridor plus a table from OSM
way id to corridor. A corridor is a run of ways with the same ref (or name), highway
class and eligibility, joined where exactly two of them meet. Unlabelled ways join
only where no other road meets them; roundabouts never join.

Residential, living street, service and motorway roads, slip roads, roundabouts and
roads at 30 mph or less get no score. The speed limit comes from, in order: a
`maxspeed` tag; a national-limit tag (`maxspeed=national`, `maxspeed:type`,
`source:maxspeed`); `lit=yes` on a non-trunk road (30 mph); being more than half
inside a settlement (30 mph); otherwise national speed limit, assumed.

Each eligible corridor gets six components from 0 to 1 and a score out of 100:

| Component | Weight | Measure |
| --- | --- | --- |
| Curvature | 0.30 | Metres per km inside bends of radius < 150 m lasting >= 60 m (geometry resampled every 10 m, radius measured across 40 m); full marks at 250 m/km |
| Road class | 0.15 | tertiary 1.0, secondary 0.9, unclassified 0.9, primary 0.5, trunk 0.2 |
| Speed limit | 0.15 | 40 mph 0.3, 50 mph 0.7, 60 mph 1.0, 70 mph 0.8 |
| Junctions | 0.15 | Side roads per km inside the corridor, signals and roundabouts double; 1.0 at <= 2/km, 0 at >= 10/km |
| Settlement | 0.15 | Share inside `landuse` residential/retail/commercial or near a `place` node (village 400 m, hamlet 150 m); 1.0 at <= 10%, 0 at >= 60% |
| Elevation | 0.10 | Climb per km from Valhalla heights every 50 m, median-filtered, averaged over 300 m and with a 3 m dead band; full marks at 15 m/km |

Each component also has a confidence. Speed: 1.0 tagged, 0.6 from lighting or a
settlement, 0.3 assumed. Curvature: 1.0 up to 50 m mean node spacing, falling to 0.5
at 200 m. Settlement: 0.9, or 0.6 when a place node is the only evidence. Junctions
0.9, road class 1.0, elevation 0.6 (0 without heights). The corridor confidence is the
weighted mean, multiplied by 0.9 for the share of the corridor whose surface is
presumed paved rather than tagged. Corridors below 0.6 confidence, or shorter than
1 km, are stored but not recommended.

**Why.** OSM splits roads at arbitrary points, so curvature measured per way would cut
bends in half; joining ways first fixes that. Scoring OSM ways rather than Valhalla
edges keeps the scoring testable without a server, uses OSM's own geometry rather
than Valhalla's simplified shapes, and Stage 3 can still map any route back to
corridors through the way ids from `trace_attributes`. The speed limit gates
everything else, which is why its inference is explicit and its source is stored.

The elevation smoothing exists because Stage 1 measured 428 m of climbing between
Reading and Newbury from raw heights. On a synthetic test, 10 km of flat road with
4 m of noise gives over 300 m of raw climb and under 25 m after smoothing, while a
rolling profile with about 70 m of real climb keeps more than three quarters of it.

Two changes from the approved plan. Slip roads and roundabouts were added to the
roads that never score: a roundabout is a 20 m radius circle and would otherwise top
the curvature scale. And the curvature confidence floor was raised from 0.3 to 0.5,
because straight roads are legitimately drawn with few nodes and the original curve
marked every straight A road as low-confidence.

**Revisit when** the reference roads are ranked (`make evaluate`). Every weight and
threshold above is a first guess. The confidence threshold may also move once the
first real build shows how much of the region has an assumed speed limit.

## 2026-10-01: A generated UK boundary for Valhalla

**Decision.** The last step of the extract pipeline adds one administrative
boundary, tagged as the United Kingdom (`ISO3166-1=GB`, `admin_level=2`) and drawn
as a rectangle slightly larger than the clip box, to `region-filtered.osm.pbf`.
Its ids start at 10^12, far above any real OSM id, so the merged file stays sorted.
A first version supplied it as a separate file with negative ids, and Valhalla's
tile builder aborted with "Detected unsorted input data".

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
