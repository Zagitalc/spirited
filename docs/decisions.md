# Decisions

Newest first. Each entry says what was decided, why, and what would make us
revisit it.

## 2026-10-02: `lanes=2` does not show that an unclassified road is wide

**Decision.** Only a `width` or `est_width` of 5 m or more clears the "possibly narrow"
penalty on an unclassified road. A `lanes=2` tag no longer does.

**Why.** The first reference-road run put Back Lane (Wasing to Woolhampton), a road
LonZac disliked and confirmed on street view to be single track, above every road they
liked. Its tags were `highway=unclassified`, `lanes=2`, `maxspeed=60 mph`,
`surface=asphalt` and `source:name=OS-OpenData_StreetView`. The `lanes=2` tag
cleared the narrow penalty. It looks like a default (two-way, so two lanes) rather than
a measurement, and there is no way to tell the two apart from the tags.

**Cost.** A genuinely two-lane unclassified road tagged `lanes=2` and nothing else now
loses a quarter of its score. A `width` tag of 5 m or more removes that. On the
ten reference roads this one change puts all five liked roads above all five
disliked ones, but by 1.8 points, so it needs checking on roads not used to find it.

## 2026-10-02: How loops are generated (Stage 3)

**Decision.** A loop is built from waypoints chosen on well-scored roads, not found by
searching the road network.
1. Ask Valhalla for the area reachable in 40% of the target time (an isochrone) and take
   points from the score database that lie inside it: one every 4 km along each
   recommendable corridor of at least 2 km, best-scored corridors first, spread
   around the start by bearing, at least 3 km apart, at most 16 of them and 3 per
   corridor.
2. Use one time matrix call to estimate every loop of two (and, from a 55-minute
   target, three) of those points, and keep up to 60 whose estimated time is within
   25% below or 5% above the target, favouring higher scores.
3. Route each candidate leg by leg. Each leg avoids the roads earlier legs used, by
   excluding a point every 800 m along them, except within 1.5 km of the leg's own
   ends. If no route exists, the leg is routed without the exclusions.
4. Match every route to corridors through the OSM way ids from `trace_attributes` and
   keep the loops that pass the checks in `docs/api.md`.

The numbers (55%, 15%, 2 km, 30%, 15%, the 0.85 speed factor, the tolerances and the
spacing) are first guesses and live in `backend/src/spirited/loops/config.py`. Loops
are ranked by score with a small penalty for missing the target time (a loop 10% off
loses 2.5 points). Motorways are avoided through `use_highways: 0`, and a loop that still
uses one is rejected.

**Why.** Valhalla's costing cannot see our scores, so waypoint choice is the only way
to steer it. The avoid-points step exists because a first version let legs retrace each
other: on a grid-like test network, 24 of 40 candidates repeated more than 10% of their
road. The way id alone cannot measure that, since a long OSM way is many edges, so each
edge is keyed by its way and its two ends.

**Cost.** Loops are only as good as the scores, which cannot see width. The checks reject
candidates by rule, so a start with few good roads returns fewer loops, or none, and says
why. Estimated times come from a model, not from a drive. Routing about 20 candidates
took half a second on a local test network and has not been timed on the real region.

## 2026-10-02: A local map page for looking at loops

**Decision.** `make loops` writes `out/loops/loops.html`, a page that loads Leaflet from
cdnjs and Esri's World Street Map tiles, with OpenStreetMap's own tiles as a second layer.

**Why.** Nothing so far could be looked at on a map, and scores are hard to judge as
numbers. The first version used openstreetmap.org's own tiles, which refused to load because a
page opened from a file sends no Referer. CARTO's raster tiles were tried next and now
demand an API key. Esri's tiles load without a key from a local file and are fine for one
person looking at their own results; their terms do not cover an app, so the app's
provider is still a Stage 4 decision.

## 2026-10-02: Dual carriageways never score; bare tertiary roads are not trusted

**Decision.** Two rules, both from the 16 reference roads.
- A trunk or primary road tagged `oneway`, or any road tagged `dual_carriageway=yes` or
  `expressway=yes`, is ineligible, reason `dual_carriageway`. OSM draws a dual
  carriageway as two one-way ways, so the A3290 (`dual_carriageway=yes`, 70 mph) and the
  A4 at Reading (`oneway=yes`, 40 mph) both qualify. One-way secondary and tertiary
  roads are left alone: they are rare and usually a village street.
- A tertiary way with no paved `surface` tag and no speed limit tag (so the speed is
  assumed) gets the 0.55 factor, as an unclassified road does, and is not recommended.
  Sonning Common Road, disliked as single track, has only `highway=tertiary` and a name;
  the liked Brimpton Road and Goring Lane have `lanes=2`, a surface and a speed.

**Why.** Both disliked kinds scored well above liked roads: the A3290 at 50.6 and
Sonning at 63.7. The first is two carriageways, which is not the drive Spirited is
for; the second is a road nobody has surveyed, and the safety rule is to include on
evidence.

**Cost.** The second rule drops part of the 894 km of tertiary road with no surface tag;
the build summary shows how much. A tertiary road with a speed tag but no surface tag
stays in. Tertiary roads can be single track while tagged like any other, so this rule
catches only the unsurveyed ones, not single-track roads in general.

## 2026-10-02: Unclassified roads are not recommended without evidence

**Decision.** In a corridor's confidence, the surface factor for an unclassified way is
0.55 unless the way has both a paved `surface` tag and a `width` or `est_width` of at
least 5 m. That alone puts a corridor made of such ways below the 0.6 cut-off, so it is
still scored and routable but never recommended for itself. Other classes without a
surface tag keep the 0.9 factor. (The first version only asked for a surface tag; the
reference roads showed that five disliked single-track lanes carry one, and LonZac
asked for unclassified roads to be excluded by default.)

**Why.** The project's safety rule says missing surface data on minor roads is suspect
and low-confidence segments are excluded from recommendations. The first build applied
only the 0.9 factor, so no corridor fell below the cut-off and the rule had no effect:
Mill Lane, tagged with nothing but `highway=unclassified` and a name, scored in the
90s. The Stage 0 filter lets such roads into the routing graph when they have a name;
this keeps them out of what Spirited recommends.

**Cost.** Good lanes drop out of recommendations unless OSM records their width: the
liked Warren Row Road is one. Wrongly dropping a good lane loses a suggestion; wrongly
recommending a single-track lane is the failure that matters. Adding `surface=asphalt`
and `width` in OSM brings a lane back.

## 2026-10-02: Narrow lanes score lower

**Decision.** A corridor's score is multiplied by `1 - 0.5 × narrowness`, where
narrowness is the length-weighted share of road that is narrow. A way counts as
narrow (1) when it is two-way and tagged `lanes=1` or a `width`/`est_width` under
5 m, and a whole corridor counts as narrow when it has a `highway=passing_place` node.
An unclassified way with no width tag of 5 m or more counts as possibly narrow (0.5),
so its score drops by a quarter. `lanes=2` does not clear it (see the 2026-10-02
entry on `lanes=2` below).

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
| `use_highways` | 0 | Loops avoid motorways; any loop that still uses one is rejected |

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

## 2026-10-02: Planned loop times are corrected by what routing shows

**Decision.** The matrix gives each candidate a planned time. After four candidates have
been routed, the median ratio of routed to planned time scales the plans that remain, and
those that would miss the tolerance are skipped. The planning window is wider
(30% below, 15% above) and up to 100 plans are kept.

**Why.** On the real region, 21 of 29 candidates failed on time. Routing each leg around
the roads the earlier legs used adds detours the matrix cannot see, so loops come out
longer than planned and a fixed window is aimed in the wrong place. The correction is a
single median, which is crude: it assumes detours cost about the same proportion for every
candidate. If that proves false the fix is to route fewer, better-chosen loops, not a
cleverer correction.

## 2026-10-03: Loop limits eased after the first real runs

**Decision.** Time tolerance 10% to 15%, minimum recommended share 60% to 55%, maximum
built-up share 25% to 30%. The limit on road we cannot vouch for (15%, no stretch over
2 km) is unchanged.

**Why.** With the original limits, three start points taken from the reference roads gave
no loops at all. With a tolerance of 20%, 50% and 35%, Brimpton gave two loops and
Waltham St Lawrence three. LonZac preferred the loops at 76% and 72% recommended road
(18% and 26% built up) to the one at 70% (28% built up), so the built-up limit is set
just above that and not at the 35% tried. The time tolerance stops at 15% because a loop
that misses by more than that is the wrong answer, not a looser one. Brimpton's loops
scored about 37 against 45 to 48 elsewhere: the area has little recommended road, and
easing the limits there trades quality for having any loop. This rests on three start
points and one person's opinion.

## 2026-10-03: Plan for the detours routing adds

**Decision.** Candidates are planned as if routing adds 25% to the matrix's estimate
(`detour_prior`), from the first candidate, and the measured median replaces that after
four have been routed. Candidates whose time would still miss are skipped. The planning
window on the raw estimate is wide (45% below the target, 15% above) so a wrong prior
cannot hide the right candidates.

**Why.** Routing added a median of 24% at Watlington and 25% at Kintbury, so the loops
were being planned about a quarter short and the first four routed candidates were mostly
wasted. Kintbury then gave three loops (Watlington one). The prior comes from two start
points and may differ in other country, which is why it is replaced by the measured value.

## 2026-10-03: Skip a plan only if no plausible detour fits

**Decision.** Replaces the skipping rule of the previous entry. A planned candidate is
skipped only if it misses the time at both ends of the detour range (1.0 to 1.7 times the
matrix estimate, widened if routing shows more). The 25% prior now only orders candidates.

**Why.** Through the API, Kintbury gave one loop from 22 candidates where the command line
had given three from 8 before the prior was added. The likely cause: detours differ a lot
from loop to loop, and the loops that pass are those with small detours, which the median
prior (and the median after four routed) skipped. This is an inference from the numbers, to
be confirmed by rerunning Kintbury. Cost: more candidates are routed per request.

## 2026-10-03: Rank candidates two ways and try them in turn

**Decision.** Candidates are ranked once at face value and once allowing 25% for detours,
and the two lists are interleaved. The planning window above the target goes back to 15%.

**Why.** The previous entry's fix did not bring Kintbury back to three loops: one loop from
38 candidates, against three from 8 before the detour prior existed. Of the loops lost,
one (102 minutes) had a raw estimate above the 10% window set in the same patch, and
ranking by the expected detour pushes loops with almost no detour behind others that then
fail on time, and the similar-anchors filter drops them. Interleaving keeps the old order
as half of the candidates. This is again inference, not a measurement; the Kintbury rerun
decides it.

## 2026-10-04: Map tiles from OpenFreeMap, and the API on the local network

**Decision.** The app draws its map from OpenFreeMap's public vector tiles through
MapLibre Native. During Stage 4 the phone reaches the backend on the developer's own
network (`make backend-run-lan`), with plain HTTP allowed in debug builds only.

**Why.** OpenStreetMap's own raster tiles are not for apps and Esri's terms do not cover
one. A keyed provider needs an account and a secret the repository must not hold.
OpenFreeMap's terms (read by LonZac, 2026-10-04) allow use in an app with attribution and
no key. The local network is the only place the backend runs until Stage 5.

**Risks accepted.** OpenFreeMap has no SLA and can be discontinued, so the style URL sits
in one constant and self-hosted tiles are the fallback. The app must not prefetch tiles.
The API has no login, so it must stay off the public internet until Stage 5 adds hosting
and the questions that come with it.

## 2026-10-04: Each segment carries its own geometry, and the response is pinned

**Decision.** Every segment of a loop in `POST /loops` now includes its `geometry`, and a
test fixes the exact fields of the response, a loop and a segment.

**Why.** The Android app is the second client. Cutting the line by distance in Kotlin
would repeat the work `make loops` already does in Python, and the two maps could disagree
about which stretch is which. The backend decides, both clients draw what it says. Pinning
the fields means the API and the app can change only together, deliberately. The cost is a
larger response, since segment lines repeat the loop's own points once.

## 2026-10-04: Plain MapLibre Native in Compose, and the map screen's state

**Decision.** The app uses MapLibre Native Android 13.6.1 directly, wrapped in an
`AndroidView`, rather than a Compose wrapper library. The start point and camera are kept
in Compose saved state for now and move to a ViewModel when loops are requested.

**Why.** The Compose wrappers for MapLibre are young and their API is still changing, so a
version bump could break the app for reasons unrelated to Spirited. The native SDK is stable
and documented; the cost is a few lines of lifecycle code. The marker is a circle layer in
the style, not a deprecated `Marker`. MapLibre's attribution button and logo stay on, since
OpenStreetMap and OpenFreeMap require credit.

**Not yet checked.** The style address `https://tiles.openfreemap.org/styles/liberty` was
written from memory of OpenFreeMap's guide and could not be fetched from the build sandbox.
The first phone run settles it.

## 2026-10-04: Location is read once, on request, and never kept

**Decision.** The app asks for location permission only when the person taps "Use my
location", reads one position through the platform's `LocationManager`, and uses it as the
start point. Coarse permission is enough. There is no background location, no tracking and
no Google Play services dependency.

**Why.** The project has no accounts and no live navigation, and a drive planner needs a
start point, not a trail. Asking at the moment of use explains itself; asking at launch
does not. The cost is a slower first fix indoors than Google's fused provider would give,
and a person who refuses permission falls back to long-pressing the map, which still works.

## 2026-10-04: Requests, state and errors in the app

**Decision.** The app talks to the backend with OkHttp and kotlinx.serialization. The chosen
start, drive time, backend address and the last answer live in a ViewModel, so rotation and
backgrounding do not lose them. Changing the start or the time cancels a request in flight
and drops its answer; a second tap on Find loops while waiting does nothing. The backend
address is a setting (default the emulator's `10.0.2.2`), with a Save and test button, and
plain HTTP is allowed in debug builds only. Four failures get four different messages: the
backend refused the start (422, with its reason), it is not ready (503), nothing answered
(wrong address or another network), and the answer was not readable.

**Why.** A phone cannot say "network error" and leave a person guessing; the three causes
need three different fixes, and the first one we hit in practice was a phone on another
network. The response is parsed with unknown fields ignored, so a backend that adds a field
does not break an installed app, while the backend's own test pins the fields that exist.

**Found on the way.** A segment at the very end of a loop could get a line of one point,
which is not a valid line. The backend now always returns at least two points.

**Not yet checked.** The screens are untested on a device; the API layer has JVM tests,
including one that reads a response produced by the backend's own code.

## 2026-10-04: Built-up road near the start and end is not counted against a loop

**Decision.** In the checks on a loop's shares of recommended and built-up road, built-up
kilometres within 4 km of the start or of the end (measured along the route) are left out of
both the numerator and the length. The cap on roads we cannot vouch for is unchanged. The
shares reported to the app still count every kilometre, and `--town-allowance` on the command
line changes the 4 km.

**Why.** LonZac's phone test from two starts in Caversham gave no loop and one loop. Most
people start where they live, which is a town, and the road out of it is not the drive. Checking the
whole loop made the cost of leaving a town fall on every start in one. Leaving the lane cap
alone keeps the safety rule: the allowance excuses streets, not roads we have no evidence for.

**Risks accepted.** A loop can now be up to 8 km of streets, 4 at each end, on top of the
30% built-up limit measured on the rest. Unreported: whether that gives good loops from the
two Caversham starts; that needs a rerun on the real data.

## 2026-10-04: Loops are drawn from the backend's segments, one loop at a time

**Decision.** The app draws only the chosen loop, as one line per segment coloured by the
`group` the backend gave it (green recommended, orange cannot vouch for, grey built up), over
a white casing so it reads on any map. The other loops are cards under the map. An unknown
group is drawn grey. The app never works out what kind of road a stretch is.

**Why.** Two loops drawn together on one map are hard to tell apart on a phone, and the card
is where the numbers and warnings go. Taking the group from the backend keeps the phone and
the dev map page in agreement, and means a change to the rules is a backend change only.
The colours are not colour-blind safe on their own: the legend names them, and a later pass
can add dashes for the orange stretches.

## 2026-10-04: GPX is shared as a file through Android's share sheet

**Decision.** The chosen loop's GPX, exactly as the backend sent it (a track, not a route), is
written to the app's cache and shared with `ACTION_SEND` through a `FileProvider`. There is no
storage permission and no export folder; the previous file is deleted before the next is written.

**Why.** The share sheet lets the person choose the navigation app, so Spirited needs no deep
links into any of them, and a cache file needs no permission. The backend already produces the
GPX and tests it, so the app does not build one.

**Not yet checked.** Whether the track opens correctly in a real navigation app on the phone,
and that its timings are believable. A track with no times is a line to follow, not a route
the app can recalculate if the driver leaves it; that limit belongs in the README until
a navigation app has been tried.

## 2026-10-04: Segment lines overlap by one point

**Decision.** Each segment's line now includes the first point of the next segment.

**Why.** LonZac saw a gap in a drawn loop. A segment boundary can fall inside a long straight
span between two points of the route; the points before it went to one segment and the points
after it to the next, so the span itself was drawn by neither. The GPX and the loop's own line
were unbroken, which is how this was told apart from a routing fault. The overlap is one span
of the next segment's colour under that segment's own line, which is not visible.

## 2026-10-04: Landscape puts the panel beside the map

**Decision.** With the phone on its side the controls sit in a 360 dp column to the right of
the map instead of under it, and the map is fitted to a loop only when a loop is received or
chosen, not when the screen is recreated by a rotation.

**Why.** The first rotation test on LonZac's phone left a strip of map a few pixels tall,
zoomed out to the whole country: the panel took the full screen and the map refitted itself
to the loop while it had almost no height. State survived the rotation; the layout did not
cope with it.

**Not yet checked.** The new layout has not been seen on a device, and tablets and split screen
may need their own rules.

## 2026-10-04: Loops may not turn back down a road

**Decision.** A loop is turned down if it drives along the same road in the opposite direction for
more than 0.5 km in one go. The first and last 4 km are exempt. `--max-retrace` on the command
line changes the 0.5 km.

**Why.** LonZac saw a loop near Binfield that drove down a spur and came back along it. A spur of
about 2 km is under the 10% limit on repeated road, which measures the total and not the shape, so
it passed. A U-turn is also a bad drive in itself. The exemption is there because a start on a
dead-end road has to leave by the way it came.

**Risks accepted.** The 0.5 km is a guess. A loop that has to use a short out-and-back to reach a
good road is rejected, and fewer loops may come back from some starts. Unverified on real data
here: that needs a rerun from the Caversham starts.

## 2026-10-08: Retrace is measured on the route's shape as well

**Decision.** The check that rejects a loop for turning back down a road now also looks at the
shape of the route: a stretch counts as retraced where the route passes within 12 m of earlier
road going the opposite way. The same 0.5 km limit applies, and the last 4 km are still exempt.

**Why.** LonZac's rerun after the first retrace limit still showed a spur south of the B3018 near
Binfield in two of three loops. The first check compared graph edges, and a waypoint in the middle
of an edge splits it into two partial edges, so a spur that is one edge long never shows up as
driven twice. The shape cannot be fooled that way.

**Risks accepted.** Unverified on the real data: I could reproduce the edge lists only on a
synthetic map, so the shape check is the fix by reasoning and by tests, and LonZac's next run is the
evidence. A road driven past in opposite directions on separate occasions that touches for over
0.5 km would also be rejected.
