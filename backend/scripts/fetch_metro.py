"""Забирает схему московского метро из OpenStreetMap (Overpass) в metro_moscow.json.

Запускается руками при обновлении схемы (открыли станцию — перезапустили):

    python backend/scripts/fetch_metro.py

Берутся линии метро и МЦК (в OSM это route=train сети «Московский метрополитен»): станции в порядке следования по каждой линии. Расписание не нужно —
время в пути считается по средней скорости, а ожидание поезда константой (metro_provider.py).
"""

import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Москва с областью: часть станций (Мякинино, Котельники) за МКАД
BBOX = "55.35,36.80,56.10,38.05"
QUERY = f"""
[out:json][timeout:180];
(
  rel["route"="subway"]({BBOX});
  rel["route"="train"]["network"="Московский метрополитен"]({BBOX});
)->.routes;
.routes out body;
node(r.routes)->.stops;
.stops out body;
"""
OUTPUT = pathlib.Path(__file__).resolve().parent.parent / "src/services/travel/metro_moscow.json"


def fetch(attempts: int = 6) -> dict:
    """Overpass часто отвечает «сервер занят» или 429 — повторяем с паузой."""
    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "hackaton-opt/1.0 (field engineer routing prototype)"},
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read().decode()
        except urllib.error.HTTPError as error:
            print(f"попытка {attempt}: Overpass ответил {error.code}", file=sys.stderr)
            time.sleep(60)
            continue
        if body.lstrip().startswith("{"):
            return json.loads(body)
        print(f"попытка {attempt}: Overpass занят", file=sys.stderr)
        time.sleep(30)
    raise RuntimeError("Overpass не ответил данными")


def main() -> None:
    payload = fetch()
    nodes = {element["id"]: element for element in payload["elements"] if element["type"] == "node"}
    relations = [element for element in payload["elements"] if element["type"] == "relation"]

    stations: dict[tuple[str, float, float], int] = {}
    station_list: list[dict] = []
    lines: list[dict] = []

    for relation in relations:
        tags = relation.get("tags", {})
        line_ref = tags.get("ref") or tags.get("name", "")
        order: list[int] = []
        for member in relation.get("members", []):
            if member["type"] != "node" or not member.get("role", "").startswith("stop"):
                continue
            node = nodes.get(member["ref"])
            if node is None:
                continue
            name = node.get("tags", {}).get("name")
            if not name:
                continue
            # станция = остановка линии: узлы двух направлений сливаются, а одноимённые
            # станции разных линий остаются разными — между ними настоящая пересадка
            key = (line_ref, name)
            if key not in stations:
                stations[key] = len(station_list)
                station_list.append(
                    {
                        "name": name,
                        "line": line_ref,
                        "lat": round(node["lat"], 6),
                        "lon": round(node["lon"], 6),
                    }
                )
            index = stations[key]
            if index not in order:
                order.append(index)
        if len(order) < 2:
            continue
        lines.append(
            {
                "ref": line_ref,
                "name": tags.get("name", ""),
                "stations": order,
            }
        )

    # у линии два направления — оставляем по одному варианту с наибольшим числом станций
    by_name: dict[str, dict] = {}
    for line in lines:
        known = by_name.get(line["name"])
        if known is None or len(line["stations"]) > len(known["stations"]):
            by_name[line["name"]] = line

    OUTPUT.write_text(
        json.dumps(
            {
                "stations": station_list,
                "lines": sorted(by_name.values(), key=lambda line: line["name"]),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(f"{OUTPUT}: станций {len(station_list)}, линий {len(by_name)}")


if __name__ == "__main__":
    main()
