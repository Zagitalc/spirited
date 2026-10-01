# Data attribution

## OpenStreetMap

Map data © OpenStreetMap contributors, available under the
[Open Database Licence (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
See <https://www.openstreetmap.org/copyright>.

Spirited uses OpenStreetMap data in three ways:

- **Extract.** County extracts from Geofabrik are merged, clipped and filtered by the
  scripts in `backend/src/spirited/extract`. None of this data is committed to the
  repository.
- **Routing graph.** From Stage 1, Valhalla builds its graph from the filtered
  extract.
- **Scores.** From Stage 2, per-segment scores are derived from the extract. That
  score database is a derivative database under the ODbL. Running a service on it
  only needs attribution, but if it were ever distributed it would have to be offered
  under the ODbL as well.

The Android app will show "© OpenStreetMap contributors" on the map from Stage 4.

## Still to check

- Elevation data, added in Stage 1.
- The map tile provider, chosen in Stage 4.
