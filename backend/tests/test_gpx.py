import xml.etree.ElementTree as ET

from spirited.routing.gpx import to_gpx

NS = {"g": "http://www.topografix.com/GPX/1/1"}


def test_gpx_contains_every_point_in_order() -> None:
    points = [(51.45, -0.97), (51.40, -1.32)]
    root = ET.fromstring(to_gpx(points, name="Reading & Newbury"))
    trkpts = root.findall(".//g:trkpt", NS)
    assert [(float(p.get("lat", 0)), float(p.get("lon", 0))) for p in trkpts] == points
    assert root.findtext(".//g:trk/g:name", namespaces=NS) == "Reading & Newbury"
