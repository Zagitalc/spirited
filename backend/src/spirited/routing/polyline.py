"""Encoded polylines, as used by Valhalla (precision 6) and Google (precision 5)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

LatLon = tuple[float, float]


def _decode_values(encoded: str) -> Iterator[int]:
    index = 0
    while index < len(encoded):
        result = shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        yield ~(result >> 1) if result & 1 else result >> 1


def decode(encoded: str, precision: int = 6) -> list[LatLon]:
    factor = 10**precision
    values = list(_decode_values(encoded))
    points: list[LatLon] = []
    lat = lon = 0
    for dlat, dlon in zip(values[0::2], values[1::2], strict=True):
        lat += dlat
        lon += dlon
        points.append((lat / factor, lon / factor))
    return points


def _encode_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chunks = []
    while value >= 0x20:
        chunks.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunks.append(chr(value + 63))
    return "".join(chunks)


def encode(points: Iterable[LatLon], precision: int = 6) -> str:
    factor = 10**precision
    out = []
    prev_lat = prev_lon = 0
    for lat, lon in points:
        ilat, ilon = round(lat * factor), round(lon * factor)
        out.append(_encode_value(ilat - prev_lat))
        out.append(_encode_value(ilon - prev_lon))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)
