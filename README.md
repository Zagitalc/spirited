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

Stage 1 of 5. The OSM extract pipeline, the road safety filter and car routing with
Valhalla exist. There is no scoring, loop generation or usable app yet.

| Stage | What | State |
| --- | --- | --- |
| 0 | Foundations: structure, tooling, OSM extract | Done |
| 1 | Routing with Valhalla | In progress |
| 2 | Road scoring | Not started |
| 3 | Loop generation and HTTP API | Not started |
| 4 | Android app | Not started |
| 5 | Hosting and release | Not started |

## Layout

```
backend/   Python service: extract pipeline, road filter, later scoring and the API
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

`make backend-test`, `make extract`, `make routing` and `make android` are shortcuts for the same
commands.

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

## Limitations

- The map data is only as good as OpenStreetMap. Surface and access tags are
  incomplete, which is why the filter is cautious.
- Coverage is limited to a box around Berkshire, from roughly Swindon to the western
  edge of London and from Oxford to Guildford.
- Nothing has been tested on a phone yet.

## Data and licences

The code is under the Apache License 2.0 (see `LICENSE`).

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the Open Database Licence. Extracts are downloaded from
[OpenStreetMap France](https://download.openstreetmap.fr/extracts/) or
[Geofabrik](https://download.geofabrik.de/). See `docs/attribution.md` for details.
