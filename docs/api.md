# HTTP API

This is the contract between the backend and any client. It must not assume an
Android client: anything a client needs is described here, in plain JSON over HTTP.

There are no accounts and nothing is stored. Every request stands on its own.

## `GET /health`

Returns `200` when the service is running.

```json
{ "status": "ok", "version": "0.1.0" }
```

## `POST /loops`

Circular drives from a start point, built around roads Spirited scores well.

Request:

```json
{
  "start": { "lat": 51.4046, "lon": -1.4430 },
  "duration_min": 90,
  "count": 3
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `start.lat`, `start.lon` | number | Where the drive starts and ends. Must be inside the covered area and near a road. |
| `duration_min` | integer, 20 to 240 | Target drive time. Each loop takes this long give or take 10%. |
| `count` | integer, 1 to 5, default 3 | The most loops to return. |

Response `200`:

```json
{
  "loops": [
    {
      "distance_km": 74.6,
      "duration_min": 90,
      "score": 63.4,
      "shares": { "recommended": 0.81, "not_recommended": 0.07, "built_up": 0.12 },
      "reuse_share": 0.03,
      "geometry": { "type": "LineString", "coordinates": [[-1.443, 51.4046], "..."] },
      "polyline": "encoded polyline, precision 6 (lat, lon)",
      "gpx": "<?xml version=\"1.0\" ...",
      "segments": [
        { "from_km": 0.0, "to_km": 6.2, "road": "B4000", "group": "recommended", "score": 68.0 },
        { "from_km": 6.2, "to_km": 7.0, "road": "Mill Lane", "group": "not_recommended", "score": null }
      ],
      "warnings": ["7% of this loop is on roads we cannot vouch for"]
    }
  ],
  "notes": []
}
```

- `duration_min` is an estimate: Valhalla's free-flow time divided by 0.85, because real
  drives on country roads are slower. It does not know about traffic.
- `score` is the length-weighted mean of the road scores along the loop, from 0 to 100,
  with anything that is not a recommended road counting as 0. The scores themselves
  are first guesses (see `docs/decisions.md`), so treat this as a way to rank loops from
  the same start, not as a measure of how good a drive is.
- Every stretch is in one `group`. `recommended`: a road Spirited would recommend.
  `not_recommended`: a road it cannot vouch for, such as an unclassified lane, a road with
  little evidence in OpenStreetMap, or a dual carriageway. `built_up`: villages, residential
  streets, roundabouts and slip roads. `shares` give each group's share of the loop's
  length. `score` is set only for `recommended` segments.
- `segments` are in driving order. A client can cut `geometry` at `from_km` and
  `to_km` (measured along the route) to colour it.
- `geometry` is GeoJSON, so coordinates are `[lon, lat]`. `polyline` is Google's
  encoding at precision 6 and stores `(lat, lon)`.
- `warnings` are plain sentences about this loop, safe to show to a person.
- `notes` are about the request. When fewer than `count` loops were found, a note says
  why, for example how many candidates were dropped and for what reason. `loops` can
  be empty with a `200`: that means no loop passed the checks, not that the service
  failed.

A loop passes only if it takes the requested time, has at least 60% of its length on
recommended roads, at most 15% on roads in `not_recommended` (and no stretch of those
over 2 km), at most 25% built up, repeats at most 10% of its own roads, stays clear of the
edge of the data and uses no motorway.

Errors:

| Status | When |
| --- | --- |
| `422` | The request is malformed, the start is too close to the edge of the covered area, or no road could be found near it. The body is `{"detail": ...}`. |
| `503` | The routing service is not running, or the road scores have not been built. |
