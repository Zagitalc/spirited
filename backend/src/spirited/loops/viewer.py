"""A single local HTML page that draws loops on a map, for looking at them by eye.

The page loads Leaflet from a CDN and OpenStreetMap's standard tiles, which is fine for
a person looking at their own results but not for an app. The tile provider for the
app is a Stage 4 decision.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import numpy as np

from spirited.loops.generate import Loop
from spirited.routing.polyline import LatLon
from spirited.scoring.geometry import segment_lengths, to_xy


def _along_km(points: Sequence[LatLon]) -> np.ndarray:
    xy = to_xy(np.array([[lon, lat] for lat, lon in points]))
    return np.concatenate([[0.0], np.cumsum(segment_lengths(xy))]) / 1000


def segment_paths(loop: Loop) -> list[dict[str, Any]]:
    """Each segment of a loop with the part of the line that belongs to it.

    Segment distances come from Valhalla's edge lengths and the line from its shape, so
    the two differ slightly; distances are scaled to the line before it is cut.
    """
    along = _along_km(loop.points)
    scale = along[-1] / loop.segments[-1].to_km if loop.segments[-1].to_km else 1.0
    paths = []
    for segment in loop.segments:
        first = int(np.searchsorted(along, segment.from_km * scale, side="left"))
        end = int(np.searchsorted(along, segment.to_km * scale, side="right"))
        # A line needs two points, even for a short segment at the very end of the loop.
        first = min(first, len(loop.points) - 2)
        piece = loop.points[first : max(end, first + 2)]
        paths.append(
            {
                "path": [[lat, lon] for lat, lon in piece],
                "road": segment.road,
                "group": segment.group.value,
                "score": segment.score,
                "km": round(segment.to_km - segment.from_km, 2),
            }
        )
    return paths


def _summary(loop: Loop) -> dict[str, Any]:
    return {
        "km": round(loop.distance_km, 1),
        "minutes": round(loop.duration_min),
        "score": round(loop.score, 1),
        "shares": {group.value: round(share * 100) for group, share in loop.shares.items()},
        "reuse": round(loop.reuse_share * 100),
        "warnings": list(loop.warnings),
        "waypoints": [list(point) for point in loop.waypoints],
        "segments": segment_paths(loop),
    }


def render(start: LatLon, minutes: float, loops: Sequence[Loop], notes: Sequence[str]) -> str:
    data = {
        "start": list(start),
        "minutes": minutes,
        "loops": [_summary(loop) for loop in loops],
        "notes": list(notes),
    }
    payload = json.dumps(data).replace("</", "<\\/")
    return _TEMPLATE.replace("__DATA__", payload)


_TEMPLATE = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spirited loops</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<style>
  html, body { height: 100%; margin: 0; font: 15px/1.4 system-ui, sans-serif; color: #1c1c1c; }
  #app { display: flex; height: 100%; }
  #side { width: 340px; overflow-y: auto; padding: 16px; box-sizing: border-box;
          border-right: 1px solid #ccc; background: #fafafa; }
  #map { flex: 1; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .loop { border: 1px solid #ccc; border-radius: 6px; padding: 10px; margin: 10px 0;
          background: #fff; cursor: pointer; }
  .loop.on { border-color: #1b6e3c; box-shadow: 0 0 0 2px #1b6e3c33; }
  .loop b { font-size: 16px; }
  .muted { color: #555; }
  .warn { color: #8a4b00; }
  .key span { display: inline-block; width: 22px; height: 6px; margin: 0 6px 2px 0; }
  .note { background: #fff4e0; padding: 8px; border-radius: 6px; margin: 10px 0; }
  @media (max-width: 700px) {
    #app { flex-direction: column-reverse; }
    #side { width: auto; height: 45%; border-right: 0; border-top: 1px solid #ccc; }
  }
</style>
</head>
<body>
<div id="app">
  <div id="side">
    <h1>Spirited loops</h1>
    <div class="muted" id="intro"></div>
    <div id="notes"></div>
    <div id="list"></div>
    <p class="key muted">
      <span style="background:#1b6e3c"></span>recommended road (darker is higher scoring)<br>
      <span style="background:#e07b00"></span>road we cannot vouch for<br>
      <span style="background:#8a8a8a"></span>built-up or unscored<br>
    </p>
  </div>
  <div id="map"></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<script>
const DATA = __DATA__;
const map = L.map("map");
const esri = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
  {
    maxZoom: 19,
    attribution: "Tiles &copy; Esri, HERE, Garmin, OpenStreetMap contributors",
  }
).addTo(map);
// openstreetmap.org refuses pages without a Referer, which a file:// page never sends, so
// this layer works only if the page is served over http (python3 -m http.server).
const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>" +
    "OpenStreetMap</a> contributors",
});
L.control.layers({ "Esri streets": esri, "OpenStreetMap": osm }).addTo(map);
let layer = L.layerGroup().addTo(map);

function colour(seg) {
  if (seg.group === "recommended") {
    const t = Math.max(0, Math.min(1, (seg.score - 30) / 50));
    return `hsl(140, 65%, ${58 - 30 * t}%)`;
  }
  return seg.group === "not_recommended" ? "#e07b00" : "#8a8a8a";
}

function show(i) {
  layer.clearLayers();
  const loop = DATA.loops[i];
  let bounds = L.latLngBounds([DATA.start, DATA.start]);
  for (const seg of loop.segments) {
    const line = L.polyline(seg.path, { color: colour(seg), weight: 5, opacity: 0.9 })
      .bindTooltip(`${seg.road}, ${seg.km} km` + (seg.score === null ? "" : `, score ${seg.score}`))
      .addTo(layer);
    bounds.extend(line.getBounds());
  }
  for (const w of loop.waypoints) {
    L.circleMarker(w, { radius: 5, color: "#333", fillOpacity: 1, fillColor: "#fff" }).addTo(layer);
  }
  L.circleMarker(DATA.start, { radius: 8, color: "#b00020", fillOpacity: 1, fillColor: "#b00020" })
    .bindTooltip("start").addTo(layer);
  map.fitBounds(bounds, { padding: [30, 30] });
  document.querySelectorAll(".loop").forEach((el, j) => el.classList.toggle("on", j === i));
}

document.getElementById("intro").textContent =
  `Target ${DATA.minutes} minutes from ${DATA.start[0].toFixed(4)}, ${DATA.start[1].toFixed(4)}. ` +
  `Times assume real speeds of about 85% of free flow.`;
for (const note of DATA.notes) {
  const div = document.createElement("div");
  div.className = "note";
  div.textContent = note;
  document.getElementById("notes").appendChild(div);
}
if (!DATA.loops.length) {
  map.setView(DATA.start, 11);
  L.circleMarker(DATA.start, { radius: 8, color: "#b00020" }).addTo(map);
}
DATA.loops.forEach((loop, i) => {
  const div = document.createElement("div");
  div.className = "loop";
  const s = loop.shares;
  div.innerHTML = `<b>Loop ${i + 1}</b> &middot; score ${loop.score}<br>` +
    `${loop.km} km, about ${loop.minutes} min<br>` +
    `<span class="muted">${s.recommended}% recommended, ${s.not_recommended}% not, ` +
    `${s.built_up}% built-up, ${loop.reuse}% repeated</span>` +
    loop.warnings.map(w => `<br><span class="warn">${w}</span>`).join("");
  div.onclick = () => show(i);
  document.getElementById("list").appendChild(div);
});
if (DATA.loops.length) show(0);
</script>
</body>
</html>
"""
