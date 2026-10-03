# Spirited

Spirited plans circular drives for a car, starting with Berkshire and the counties
around it. You give it a start point and how long you want to drive for, say 90
minutes, and it comes back with three loops that do not share many roads, each with
a score breakdown and an elevation profile. You can export a loop as GPX or open it
in another navigation app.

Most route planners that look for "good" roads are built for motorcycles and lean on
curvature. Round here that mostly finds housing estates and slip roads. Spirited is
built for cars and scores a road on several things: sustained bends, road class,
speed limit, how often you meet junctions and villages, and elevation change.

## Status

Stage 3 of 5. The OSM extract pipeline, the road safety filter, car routing with
Valhalla, road scoring and a first version of loop generation exist. The scoring
weights and the loop limits are first guesses that have been checked against sixteen
roads and no real loops yet. There is no usable app yet.

| Stage | What | State |
| --- | --- | --- |
| 0 | Foundations: structure, tooling, OSM extract | Done |
| 1 | Routing with Valhalla | Done |
| 2 | Road scoring | Done |
| 3 | Loop generation and HTTP API | In progress |
| 4 | Android app | Not started |
| 5 | Hosting and release | Not started |

## Layout

```
backend/   Python service: extract pipeline, road filter, scoring, later the API
routing/   Valhalla configuration (from Stage 1)
android/   Kotlin and Jetpack Compose client
docs/      API contract, decisions log and data attribution
```

## Setting up

You need Git, [uv](https://docs.astral.sh/uv/), osmium-tool, Docker (from Stage 1)
and Android Studio.

| Tool | macOS | Windows | Linux (Debian, Ubuntu) |
| --- | --- | --- | --- |
| uv | `brew install uv` | installer from astral.sh, inside WSL 2 | installer from astral.sh |
| osmium-tool | `brew install osmium-tool` | `sudo apt install osmium-tool` inside WSL 2 | `sudo apt install osmium-tool` |
| Docker | Docker Desktop or OrbStack | Docker Desktop with the WSL 2 backend | Docker Engine |
| Android Studio | latest stable | latest stable, on Windows itself | latest stable |

On Windows, run the backend and the data scripts inside WSL 2 and Android Studio on
Windows. Leave about 10 GB free for map data.

### Backend

```sh
cd backend
uv sync
uv run pytest -q
uv run uvicorn spirited.api:app --reload   # then open http://127.0.0.1:8000/health
```

### Map data

```sh
cd backend
uv run python -m spirited.extract all
uv run pytest -q -m extract
```

This downloads the England extract (about 1.5 GB, so it takes a while), clips it to
the region box and applies the road safety filter. It tries the OpenStreetMap France
mirror first and Geofabrik second, moving on if a mirror fails or sends nothing for
60 seconds. To use another source, pass `--url <address of an England .osm.pbf>`.
The download is kept, so later runs reuse it unless the mirror has a newer file. The
output goes to `backend/data/osm/`, which is not committed:

- `region-filtered.osm.pbf`: the extract Valhalla will be built from
- `filter-report.json`: how many roads were excluded, and why
- `excluded-ways.csv`: every excluded way, so you can look up a road you know
- `manifest.json`: the source file, its checksum and download time

### Android

Open `android/` in Android Studio, or from the command line:

```sh
cd android
./gradlew assembleDebug
```

There is nothing to see yet beyond a placeholder screen.

### Routing

Needs Docker Desktop and the map data from the previous step. From the repository
root:

```sh
make routing        # builds Valhalla's tiles on first run, then serves on :8002
```

Then, from `backend`:

```sh
uv run pytest -q -m valhalla
uv run python -m spirited.routing 51.4560,-0.9690 51.4014,-1.3231 --gpx reading-newbury.gpx
```

The second command prints the distance, time, the main roads used and the climbing,
and writes a GPX file you can open in any map viewer. See `routing/README.md` for
rebuilding after the map data changes.

### Scoring

With Valhalla running (it supplies the heights), from the repository root:

```sh
make scores         # scores every road and writes backend/data/scores.sqlite
make evaluate       # ranks the roads in backend/data/reference_roads.json
```

`make evaluate` needs the reference roads filled in first: each is a road you like or
dislike, given as two points near its ends. The report ranks them by score, shows
each part of the score, and lists any roads nearby that the safety filter removed.
Add `--detail` (`cd backend && uv run python -m spirited.scoring evaluate --detail`) to
also see, for each road, the corridors it uses with links to them on OpenStreetMap, its
bends measured at several radii, and its climb.

### Loops

With Valhalla running and `make scores` done, from the repository root:

```sh
make loops START=51.4046,-1.4430 MINUTES=90
```

This writes up to three loops to `out/loops/`: one GPX file each, and `loops.html`,
which draws them on a map. Open that page in a browser. Roads are coloured by score,
orange where a stretch is on roads Spirited cannot vouch for, and grey where it is built
up. The page loads Leaflet and Esri's map tiles from the internet, for looking at
your own results only. The same loops come from `POST /loops` once the API is running
(`make backend-run`); see `docs/api.md`.

`make backend-test`, `make extract`, `make routing`, `make scores`, `make loops` and
`make android` are shortcuts for the same commands.

## Which roads Spirited will use

Roads are excluded unless there is evidence that an ordinary car can use them. The
filter in `backend/src/spirited/roadfilter.py` removes a road before the router sees
it if any of these are true:

- it is a track, service road, path, bridleway, byway or an unknown highway type
- access, `motor_vehicle` or `motorcar` tags do not positively allow cars
- it has an unpaved surface, a `tracktype` other than `grade1`, poor smoothness, a
  ford, or a byway or bridleway designation
- it is an unclassified road with no surface tag and no name or road number

The last rule will drop some perfectly good country lanes that are simply under-tagged
in OpenStreetMap. That is deliberate: a missing lane costs a slightly worse loop,
whereas routing someone down a farm track costs a lot more.

## How a road is scored

Roads are joined into corridors: runs of the same road between junctions where it
changes. Residential roads, slip roads, roundabouts, motorways, dual carriageways and
anything with a speed limit of 30 mph or less get no score. Everything else is scored from 0 to 100 on
six things:

| Part | Weight | What it rewards |
| --- | --- | --- |
| Curvature | 30% | Bends tighter than 150 m radius that last at least 60 m; single kinks don't count |
| Road class | 15% | B and C roads over A roads, and A roads over trunk roads |
| Speed limit | 15% | National speed limit over 50 and 40 mph |
| Junctions | 15% | Few side roads, traffic lights and roundabouts per km |
| Settlements | 15% | Little of the road inside towns and villages |
| Elevation | 10% | Rolling roads, from heights smoothed over 300 m |

A road known to be single track or narrower than 5 m has its score halved. An
unclassified road loses a quarter unless its width is tagged as 5 m or more, because
most narrow lanes are unclassified and few are tagged as narrow. A `lanes=2` tag does
not count, since it is often a default on single-track lanes.

Every score comes with a confidence from 0 to 1, which drops when a speed limit is
guessed, a road's geometry is sparse, a village is known only by its name on the map,
or a surface is presumed rather than tagged. An unclassified road
falls below the cut-off unless it has a paved surface tag and a width of at least 5 m,
because most single-track lanes in England are unclassified and OpenStreetMap rarely
records their width. Good lanes are dropped along with the bad ones. Corridors below 0.6, or shorter than
1 km, are not recommended. The weights are a first guess, to be tuned against a set of
reference roads with known verdicts (see `docs/decisions.md`).

## Limitations

- The map data is only as good as OpenStreetMap. Surface and access tags are
  incomplete, which is why the filter is cautious.
- Coverage is limited to a box around Berkshire, from roughly Swindon to the western
  edge of London and from Oxford to Guildford.
- Many minor roads have no speed limit in OpenStreetMap. An untagged road outside a
  village is assumed to be national speed limit, with low confidence.
- Heights come from 30 m terrain data, which cannot see cuttings, embankments or
  bridges. They are smoothed heavily, so short sharp climbs are underrated.
- The scoring has not yet been checked against enough real roads to trust its
  weights. It cannot see how wide a road is: a single-track lane with a surface and a
  speed tag looks the same as a two-lane road, and unclassified lanes are left out
  altogether, good ones included.
- Loops are built around well-scored roads, and the limits on how much of a loop may
  be on other roads (see `docs/decisions.md`) are guesses. Times assume real speeds of
  85% of Valhalla's free-flow figures, which has not been checked against a drive.
- A loop near the edge of the covered area, or from a start with only one way out, may
  retrace part of its road or be cut short.
- Nothing has been tested on a phone yet.

## Data and licences

The code is under the Apache License 2.0 (see `LICENSE`).

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the Open Database Licence. Extracts are downloaded from
[OpenStreetMap France](https://download.openstreetmap.fr/extracts/) or
[Geofabrik](https://download.geofabrik.de/). See `docs/attribution.md` for details.
