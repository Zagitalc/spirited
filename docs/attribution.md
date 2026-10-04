# Data attribution

## OpenStreetMap

Map data © OpenStreetMap contributors, available under the
[Open Database Licence (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
See <https://www.openstreetmap.org/copyright>.

Spirited uses OpenStreetMap data in three ways:

- **Extract.** The England extract from the OpenStreetMap France mirror or Geofabrik is clipped and filtered by the
  scripts in `backend/src/spirited/extract`. None of this data is committed to the
  repository.
- **Routing graph.** From Stage 1, Valhalla builds its graph from the filtered
  extract.
- **Scores.** From Stage 2, per-segment scores are derived from the extract. That
  score database is a derivative database under the ODbL. Running a service on it
  only needs attribution, but if it were ever distributed it would have to be offered
  under the ODbL as well.

The Android app will show the map's attribution control from Stage 4, with
"© OpenMapTiles" and "Data from OpenStreetMap" (see Map tiles below).

## Map tiles

The app draws its map from [OpenFreeMap](https://openfreemap.org/), whose tiles are built
from OpenStreetMap data in the OpenMapTiles schema. Its terms
(<https://openfreemap.org/tos/>) need no key or registration, allow use in an app, and
require attribution, which MapLibre shows automatically: the attribution control must stay
visible. They ban automated collection without permission, so the app must not prefetch
or bulk-download tiles. The service has no SLA and may be discontinued, so the style URL
lives in one constant in the app and self-hosted tiles are the fallback.

## Elevation

Valhalla downloads elevation from the
[Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) dataset on AWS, which
combines several public sources. Its
[attribution requirements](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
apply to anything that shows elevation, so the app's elevation profile will carry
the required credit. The exact wording is to be confirmed before release in Stage 5.

## Still to check

- The exact OpenFreeMap style URL and the MapLibre setup, to be taken from its current
  guide when the map screen is written.
