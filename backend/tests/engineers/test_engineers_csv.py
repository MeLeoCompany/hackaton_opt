"""Разбор и сборка CSV с исполнителями — без БД, справочники заданы в тесте."""

from datetime import datetime, timedelta, timezone

from src.services.engineers.engineers_csv import (
    EngineerReferenceLookup,
    build_engineers_csv,
    format_datetime,
    parse_engineers_csv,
)
from src.services.requests.requests_csv import reference_options

MOSCOW = timezone(timedelta(hours=3))

REFERENCES = EngineerReferenceLookup(
    transports=reference_options([(1, "Автомобиль"), (2, "Пешеход")]),
    skills=reference_options(
        [(1, "Локальные работы"), (2, "Работы на подключение и дозаказы"), (3, "Аварийные работы")]
    ),
)

HEADER = "id;имя;широта_старта;долгота_старта;транспорт;навыки;смена_начало;смена_конец"
GOOD_ROW = "7;Бригада Соколов;55,7400;37.658;Автомобиль;Локальные работы, 3;17.08.2026 09:00;17.08.2026 21:00"


def parse(*lines, encoding="utf-8"):
    return parse_engineers_csv("\n".join(lines).encode(encoding), REFERENCES, MOSCOW)


def test_row_with_names_and_numbers():
    result = parse(HEADER, GOOD_ROW)

    assert result.errors == []
    row = result.rows[0]
    assert row["id"] == 7
    assert row["name"] == "Бригада Соколов"
    assert row["start_latitude"] == 55.74  # запятая в дробной части тоже понимается
    assert row["transport_id"] == 1
    assert row["skill_ids"] == [1, 3]
    assert row["shift_start"].astimezone(timezone.utc).hour == 6  # 09:00 МСК


def test_engineer_without_skills_is_rejected():
    result = parse(HEADER, "8;Бригада;55.74;37.65;Пешеход;;17.08.2026 09:00;17.08.2026 18:00")

    assert result.rows == []
    assert any("навыки" in message for message in result.errors)


def test_more_than_three_skills_is_rejected():
    result = parse(
        HEADER,
        "9;Бригада;55.74;37.65;Пешеход;1,2,3,Локальные работы;17.08.2026 09:00;17.08.2026 18:00",
    )

    assert result.rows == []
    assert any("дважды" in message or "больше 3" in message for message in result.errors)


def test_shift_end_must_be_later():
    result = parse(HEADER, "10;Бригада;55.74;37.65;Пешеход;1;17.08.2026 18:00;17.08.2026 09:00")

    assert result.rows == []
    assert any("смена_конец" in message for message in result.errors)


def test_exported_file_can_be_parsed_back():
    moment = datetime(2026, 8, 17, 6, 0, tzinfo=timezone.utc)
    content = build_engineers_csv(
        [
            {
                "id": 5,
                "имя": "Бригада Мельников",
                "широта_старта": "55.706500",
                "долгота_старта": "37.739500",
                "транспорт": "Пешеход",
                "навыки": "Локальные работы, Аварийные работы",
                "смена_начало": format_datetime(moment, MOSCOW),
                "смена_конец": format_datetime(moment + timedelta(hours=12), MOSCOW),
            }
        ]
    )

    result = parse_engineers_csv(content.encode("utf-8"), REFERENCES, MOSCOW)

    assert result.errors == []
    row = result.rows[0]
    assert (row["id"], row["name"], row["transport_id"], row["skill_ids"]) == (
        5,
        "Бригада Мельников",
        2,
        [1, 3],
    )
    assert row["shift_start"] == moment
