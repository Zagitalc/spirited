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

The Android app will show "© OpenStreetMap contributors" on the map from Stage 4.

## Elevation

Valhalla downloads elevation from the
[Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) dataset on AWS, which
combines several public sources. Its
[attribution requirements](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
apply to anything that shows elevation, so the app's elevation profile will carry
the required credit. The exact wording is to be confirmed before release in Stage 5.

## Still to check

- The map tile provider, chosen in Stage 4.
