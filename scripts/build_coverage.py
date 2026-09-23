"""Зона покрытия для карт: районы и города, в которых мы действительно работаем.

Для демонстрации выгружены не все дороги и расписания страны, а окрестности наших адресов.
Чтобы оператор не гадал, где расчёт честный, карты подсвечивают зону покрытия — не пятна
вокруг точек, а настоящие границы районов Москвы и городов области из OpenStreetMap.

Как строится:
  1. берём все известные точки — геокоды обезличенных адресов (experiments/*/geocodes.json)
     и, если передан --extra, координаты из базы (офисы, старты бригад, заявки);
  2. скачиваем из Overpass границы районов Москвы и оставляем те, внутри которых есть
     хоть одна наша точка;
  3. для точек за Москвой спрашиваем у Overpass, в каком городе они лежат, и берём границу
     этого города (Домодедово, Ступино, Кашира);
  4. далёкие зоны связываем коридором по дороге (маршрут считает наш же Valhalla через API
     бэкенда) шириной CORRIDOR_KM. Это эвристика: вдоль тех же шоссе идут железные дороги,
     поэтому на карте между городами не остаётся разрывов.

Запуск (нужен поднятый бэкенд и интернет к Overpass):
    python scripts/build_coverage.py --extra points.json
"""

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEOCODES = sorted(ROOT.glob("experiments/*/geocodes.json"))

# ближе этого — одна зона; дальше — отдельная, и её свяжет коридор
GROUP_KM = 15.0
# с какого разрыва между зонами рисуем коридор: соседние районы и так сходятся встык
CORRIDOR_MIN_KM = 7.0
# ширина коридора между городами: дорога и железная дорога идут рядом
CORRIDOR_KM = 6.0
CORRIDOR_STEP_KM = 1.5
# насколько упрощаем границы: 80 метров глазу незаметны, а файл втрое меньше
SIMPLIFY_M = 80.0

EARTH_KM = 6371.0088
BASE = "http://localhost:8000/api/v1"
OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org"
OSM_API = "https://api.openstreetmap.org/api/0.6"
AGENT = "hackaton-opt/1.0 (coverage map build)"


def overpass(query: str, attempts: int = 4) -> dict:
    """Запрос к Overpass с повтором: публичный сервис иногда отвечает 429 и 504."""
    for attempt in range(attempts):
        request = urllib.request.Request(
            OVERPASS,
            data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read().decode())
        except Exception as error:  # noqa: BLE001 — ошибка сети, важен только повтор
            if attempt == attempts - 1:
                raise
            pause = 5 * (attempt + 1)
            print(f"   Overpass не ответил ({error}) — повтор через {pause} с")
            time.sleep(pause)
    raise RuntimeError("Overpass недоступен")


def distance_km(first, second):
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    half = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(
        (lon2 - lon1) / 2
    ) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(half))


def load_points(extra: Path | None) -> list[tuple[float, float]]:
    points = []
    for path in GEOCODES:
        for info in json.loads(path.read_text(encoding="utf-8")).values():
            if info.get("latitude") and info.get("longitude"):
                points.append((info["latitude"], info["longitude"]))
    if extra is not None:
        points += [(item["latitude"], item["longitude"]) for item in json.loads(extra.read_text())]
    return points


def rings_of(element) -> list[list[tuple[float, float]]]:
    """Границу собираем из внешних линий отношения: концы стыкуются, пока кольцо не замкнётся."""
    if element["type"] == "way":
        return [[(node["lat"], node["lon"]) for node in element["geometry"]]]
    pieces = [
        [(node["lat"], node["lon"]) for node in member["geometry"]]
        for member in element.get("members", [])
        if member["type"] == "way" and member.get("role") in ("outer", "") and member.get("geometry")
    ]
    return stitch(pieces)


def inside(point, ring) -> bool:
    """Луч вправо: сколько раз пересёк границу — нечётно, значит внутри."""
    latitude, longitude = point
    crossings = 0
    for (lat1, lon1), (lat2, lon2) in zip(ring, ring[1:] + ring[:1], strict=True):
        if (lat1 > latitude) != (lat2 > latitude):
            edge = lon1 + (latitude - lat1) / (lat2 - lat1) * (lon2 - lon1)
            if edge > longitude:
                crossings += 1
    return crossings % 2 == 1


def simplify_ring(ring, tolerance_m=SIMPLIFY_M):
    """Рамер-Дуглас-Пекер: убираем точки, которые не меняют форму границы."""
    if len(ring) < 3:
        return ring
    scale = math.cos(math.radians(ring[0][0]))

    def distance_to_line(point, start, end):
        x, y = point[1] * scale, point[0]
        x1, y1 = start[1] * scale, start[0]
        x2, y2 = end[1] * scale, end[0]
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            return math.hypot(x - x1, y - y1) * 111320
        area = abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1))
        return area / length * 111320

    def walk(points):
        if len(points) < 3:
            return points
        worst, index = 0.0, 0
        for position in range(1, len(points) - 1):
            gap = distance_to_line(points[position], points[0], points[-1])
            if gap > worst:
                worst, index = gap, position
        if worst <= tolerance_m:
            return [points[0], points[-1]]
        return walk(points[: index + 1])[:-1] + walk(points[index:])

    return walk(ring)


def moscow_districts(cache: Path | None = None):
    """Границы районов Москвы: одним запросом, потом отбираем нужные.

    Ответ большой (около 3 МБ), поэтому его можно сохранить рядом и не качать заново.
    """
    if cache is not None and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return [
            {"name": element["tags"].get("name", "район"), "rings": rings_of(element)}
            for element in data["elements"]
        ]
    data = overpass(
        '[out:json][timeout:240];area["name"="Москва"]["admin_level"="4"]->.moscow;'
        'rel(area.moscow)["boundary"="administrative"]["admin_level"="8"];out geom;'
    )
    if cache is not None:
        cache.write_text(json.dumps(data), encoding="utf-8")
    return [
        {"name": element["tags"].get("name", "район"), "rings": rings_of(element)}
        for element in data["elements"]
    ]


def osm_rings(kind: str, osm_id: int):
    """Границу одного объекта берём в самом OpenStreetMap: Overpass под нагрузкой отвечает 504."""
    request = urllib.request.Request(
        f"{OSM_API}/{kind}/{osm_id}/full.json", headers={"User-Agent": AGENT}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode())
    nodes = {
        element["id"]: (element["lat"], element["lon"])
        for element in data["elements"]
        if element["type"] == "node"
    }
    ways = {
        element["id"]: [nodes[node] for node in element["nodes"] if node in nodes]
        for element in data["elements"]
        if element["type"] == "way"
    }
    name = ""
    if kind == "way":
        pieces = [ways.get(osm_id, [])]
    else:
        relation = next(
            element
            for element in data["elements"]
            if element["type"] == "relation" and element["id"] == osm_id
        )
        name = relation.get("tags", {}).get("name", "")
        pieces = [
            ways[member["ref"]]
            for member in relation["members"]
            if member["type"] == "way"
            and member.get("role") in ("outer", "")
            and member["ref"] in ways
        ]
    if kind == "way":
        way = next(
            element
            for element in data["elements"]
            if element["type"] == "way" and element["id"] == osm_id
        )
        name = way.get("tags", {}).get("name", "")
    return name, stitch(pieces)


def stitch(pieces):
    """Куски границы стыкуем по концам, пока не получится замкнутое кольцо."""
    pieces = [piece for piece in pieces if len(piece) > 1]
    rings, current = [], []
    while pieces:
        if not current:
            current = pieces.pop(0)
            continue
        for index, piece in enumerate(pieces):
            if distance_km(current[-1], piece[0]) < 0.01:
                current += pieces.pop(index)[1:]
                break
            if distance_km(current[-1], piece[-1]) < 0.01:
                current += list(reversed(pieces.pop(index)))[1:]
                break
        else:
            rings.append(current)
            current = []
            continue
        if distance_km(current[0], current[-1]) < 0.01:
            rings.append(current)
            current = []
    if current:
        rings.append(current)
    return [ring for ring in rings if len(ring) >= 4]


# нас интересует населённый пункт, а не целый городской округ: он занял бы пол-области
SETTLEMENT_TYPES = ("city", "town", "village", "hamlet", "suburb", "quarter")
# и не шире этого: граница вроде «городской округ Домодедово» на карте выглядит как
# покрытие всего юга области, хотя работаем мы в одном городке
MAX_SETTLEMENT_KM = 25.0


def reverse(point, zoom):
    query = urllib.parse.urlencode(
        {"lat": point[0], "lon": point[1], "format": "json", "zoom": zoom}
    )
    request = urllib.request.Request(
        f"{NOMINATIM}/reverse?{query}", headers={"User-Agent": AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def settlement_at(point):
    """В каком населённом пункте лежит точка за Москвой: Nominatim, границу берём в OSM."""
    for zoom in (12, 14, 16):
        place = reverse(point, zoom)
        time.sleep(1.2)
        kind, osm_id = place.get("osm_type"), place.get("osm_id")
        if kind not in ("relation", "way") or not osm_id:
            continue
        if place.get("addresstype") not in SETTLEMENT_TYPES:
            continue
        name, rings = osm_rings(kind, osm_id)
        if not rings:
            continue
        span = max(
            distance_km(
                (min(latitude for latitude, _ in ring), min(longitude for _, longitude in ring)),
                (max(latitude for latitude, _ in ring), max(longitude for _, longitude in ring)),
            )
            for ring in rings
        )
        if span > MAX_SETTLEMENT_KM:
            continue
        return {"id": f"{kind}{osm_id}", "name": name or place.get("name", "город"), "rings": rings}
    return None


def ring_around(point, radius_km, steps=32):
    """Круг точками — участок вокруг адресов, которые не попали ни в район, ни в город."""
    latitude, longitude = point
    scale = math.cos(math.radians(latitude))
    return [
        (
            latitude + radius_km / 111.32 * math.sin(2 * math.pi * step / steps),
            longitude + radius_km / 111.32 / scale * math.cos(2 * math.pi * step / steps),
        )
        for step in range(steps)
    ]


def group_points(points, threshold_km=GROUP_KM):
    parent = list(range(len(points)))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first in range(len(points)):
        for second in range(first + 1, len(points)):
            if distance_km(points[first], points[second]) <= threshold_km:
                parent[root(first)] = root(second)
    groups = {}
    for index, point in enumerate(points):
        groups.setdefault(root(index), []).append(point)
    return sorted(groups.values(), key=len, reverse=True)


def centroid(group):
    return (
        sum(point[0] for point in group) / len(group),
        sum(point[1] for point in group) / len(group),
    )


def links(centers):
    if len(centers) < 2:
        return []
    joined, rest, edges = [0], list(range(1, len(centers))), []
    while rest:
        best = min(
            ((inside_index, outside) for inside_index in joined for outside in rest),
            key=lambda pair: distance_km(centers[pair[0]], centers[pair[1]]),
        )
        edges.append(best)
        joined.append(best[1])
        rest.remove(best[1])
    return edges


def simplify_path(path, step_km=CORRIDOR_STEP_KM):
    kept = [path[0]]
    for point in path[1:-1]:
        if distance_km(kept[-1], point) >= step_km:
            kept.append(point)
    kept.append(path[-1])
    return kept


def corridor_polygon(path, width_km=CORRIDOR_KM):
    """Полоса вдоль дороги: точки пути, отодвинутые влево и вправо на половину ширины."""
    half = width_km / 2
    left, right = [], []
    for index, point in enumerate(path):
        before = path[max(index - 1, 0)]
        after = path[min(index + 1, len(path) - 1)]
        scale = math.cos(math.radians(point[0]))
        dy = (after[0] - before[0]) * 111.32
        dx = (after[1] - before[1]) * 111.32 * scale
        length = math.hypot(dx, dy) or 1.0
        shift_lat = half * (dx / length) / 111.32
        shift_lon = -half * (dy / length) / 111.32 / scale
        left.append((point[0] + shift_lat, point[1] + shift_lon))
        right.append((point[0] - shift_lat, point[1] - shift_lon))
    return left + list(reversed(right))


def decode_polyline(encoded, precision=6):
    coordinates, index, latitude, longitude = [], 0, 0, 0
    factor = 10**precision
    while index < len(encoded):
        for target in ("lat", "lon"):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if target == "lat":
                latitude += delta
            else:
                longitude += delta
        coordinates.append((latitude / factor, longitude / factor))
    return coordinates


def login(login_name, password):
    request = urllib.request.Request(
        f"{BASE}/auth/login",
        method="POST",
        data=json.dumps({"login": login_name, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())["token"]


def road_path(token, origin, destination):
    request = urllib.request.Request(
        f"{BASE}/travel/route",
        method="POST",
        data=json.dumps(
            {
                "points": [
                    {"latitude": origin[0], "longitude": origin[1]},
                    {"latitude": destination[0], "longitude": destination[1]},
                ],
                "transport": 1,
            }
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Office-Id": "1",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        route = json.loads(response.read().decode())
    path = [point for piece in route["geometry"] for point in decode_polyline(piece)]
    return path or [origin, destination]


def rounded(ring):
    return [[round(latitude, 5), round(longitude, 5)] for latitude, longitude in ring]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="frontend/src/assets/coverage.json")
    parser.add_argument("--extra", help="JSON со списком {latitude, longitude} из базы")
    parser.add_argument("--districts", help="куда сложить ответ Overpass по районам Москвы")
    parser.add_argument("--login", default="shot-admin")
    parser.add_argument("--password", default="shot-pass")
    args = parser.parse_args()

    points = load_points(Path(args.extra) if args.extra else None)
    print(f"точек {len(points)}")

    print("скачиваю границы районов Москвы…")
    districts = moscow_districts(Path(args.districts) if args.districts else None)
    print(f"   районов в Москве: {len(districts)}")

    areas, covered = [], set()
    for district in districts:
        hit = [
            point
            for point in points
            if any(inside(point, ring) for ring in district["rings"])
        ]
        if not hit:
            continue
        covered.update(hit)
        areas.append(
            {
                "name": district["name"],
                "points": len(hit),
                "rings": [rounded(simplify_ring(ring)) for ring in district["rings"]],
            }
        )
    print(f"   районов с нашими адресами: {len(areas)}")

    outside = [point for point in points if point not in covered]
    # за Москвой спрашиваем про каждую точку (с точностью до километра): города стоят
    # рядом, и одна группа на всех слила бы Ступино с Каширой
    found = {}
    for point in {(round(latitude, 2), round(longitude, 2)) for latitude, longitude in outside}:
        settlement = settlement_at(point)
        if settlement is None:
            print(f"   не нашёл город для {point[0]:.3f},{point[1]:.3f} — пропускаю")
            continue
        found.setdefault(settlement["id"], settlement)
    for settlement in found.values():
        hit = [
            point
            for point in outside
            if any(inside(point, ring) for ring in settlement["rings"])
        ]
        areas.append(
            {
                "name": settlement["name"],
                "points": len(hit),
                "rings": [rounded(simplify_ring(ring)) for ring in settlement["rings"]],
            }
        )
        print(f"   город: {settlement['name']} — адресов {len(hit)}")

    covered_now = {
        point
        for point in points
        for area in areas
        if any(inside(point, [tuple(node) for node in ring]) for ring in area["rings"])
    }
    for group in group_points([point for point in points if point not in covered_now], 3.0):
        center = centroid(group)
        radius = max(1.5, max(distance_km(center, point) for point in group) + 1.0)
        areas.append(
            {
                "name": "участок",
                "points": len(group),
                "rings": [rounded(ring_around(center, radius))],
            }
        )
        print(f"   участок: адресов {len(group)}, радиус {radius:.1f} км")
    areas = [area for area in areas if area["points"]]

    token = login(args.login, args.password)
    corridors = []
    zones = [centroid([point for ring in area["rings"] for point in ring]) for area in areas]
    for first, second in links(zones):
        span = distance_km(zones[first], zones[second])
        if span < CORRIDOR_MIN_KM:
            continue
        path = simplify_path(road_path(token, zones[first], zones[second]))
        corridors.append(
            {
                "name": f"{areas[first]['name']} — {areas[second]['name']}",
                "km": round(span, 1),
                "polygon": rounded(corridor_polygon(path)),
            }
        )
        print(f"   коридор: {areas[first]['name']} — {areas[second]['name']}, {span:.0f} км")

    out = Path(args.out)
    out.write_text(
        json.dumps({"areas": areas, "corridors": corridors}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"записано: {out} ({out.stat().st_size // 1024} КБ)")


main()
