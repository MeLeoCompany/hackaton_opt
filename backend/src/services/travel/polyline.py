"""Кодирование линии маршрута в encoded polyline с точностью 6 знаков.

Valhalla отдаёт геометрию именно в этом формате, фронт его и ждёт, поэтому участки,
которые мы рисуем сами (перегоны метро), кодируются так же.
"""

from src.schemas.travel import Point

PRECISION = 1e6


def _encode_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chunks = []
    while value >= 0x20:
        chunks.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunks.append(chr(value + 63))
    return "".join(chunks)


def encode(points: list[Point]) -> str:
    """Список точек -> encoded polyline (precision 6)."""
    previous_latitude = 0
    previous_longitude = 0
    encoded = []
    for point in points:
        latitude = round(point.latitude * PRECISION)
        longitude = round(point.longitude * PRECISION)
        encoded.append(_encode_value(latitude - previous_latitude))
        encoded.append(_encode_value(longitude - previous_longitude))
        previous_latitude = latitude
        previous_longitude = longitude
    return "".join(encoded)
