"""Разбор CSV с заявками — без БД, справочники заданы прямо в тесте."""

from datetime import UTC, timedelta, timezone

from src.services.requests.requests_csv import (
    ReferenceLookup,
    WorkTypeNorm,
    parse_requests_csv,
    reference_options,
)

MOSCOW = timezone(timedelta(hours=3))

REFERENCES = ReferenceLookup(
    skills=reference_options(
        [(1, "Локальные работы"), (2, "Работы на подключение и дозаказы"), (3, "Аварийные работы")]
    ),
    priorities=reference_options([(1, "Обычная"), (2, "Срочная")]),
    transports=reference_options(
        [(1, "Автомобиль"), (2, "Пешеход"), (3, "Велосипед"), (4, "Общественный транспорт")]
    ),
    work_types=reference_options(
        [
            (1, "Подключение клиентов, базовая"),
            (2, "Авария на ТКД"),
            (4, "Локальная заявка / ремонт у клиента"),
        ]
    ),
    work_type_norms={
        1: WorkTypeNorm(skill_id=2, work_minutes=70),
        2: WorkTypeNorm(skill_id=3, work_minutes=80),
        4: WorkTypeNorm(skill_id=1, work_minutes=30),
    },
)

HEADER = "id;адрес;широта;долгота;длительность_мин;окно_начало;окно_конец;приоритет;навык;транспорт"
GOOD_ROW = "101;ул. Ленина, 1;55,7400;37.658;60;17.08.2026 18:00;17.08.2026 20:00;Срочная;аварийные работы;Автомобиль"


def parse(*lines, encoding="utf-8"):
    return parse_requests_csv("\n".join(lines).encode(encoding), REFERENCES, MOSCOW)


def test_valid_row_with_names():
    result = parse(HEADER, GOOD_ROW)

    assert result.errors == []
    row = result.rows[0]
    assert row["id"] == 101
    assert row["address"] == "ул. Ленина, 1"
    assert row["latitude"] == 55.74  # запятая в дробной части тоже понимается
    assert (row["priority_id"], row["skill_id"], row["transport_id"]) == (2, 3, 1)
    # 18:00 по Москве = 15:00 UTC
    assert row["window_start"].astimezone(UTC).hour == 15


def test_references_by_number_empty_id_and_empty_transport():
    result = parse(HEADER, ";ул. Ленина, 1;55.74;37.658;45;17.08.2026 10:00;17.08.2026 12:00;1;2;")

    assert result.errors == []
    row = result.rows[0]
    assert row["id"] is None
    assert (row["priority_id"], row["skill_id"], row["transport_id"]) == (1, 2, None)


def test_windows_1251_file_is_decoded():
    result = parse(HEADER, GOOD_ROW, encoding="cp1251")

    assert result.errors == []
    assert result.rows[0]["address"] == "ул. Ленина, 1"


def test_comma_delimiter():
    header = HEADER.replace(";", ",")
    row = '102,"ул. Ленина, 1",55.74,37.658,60,17.08.2026 18:00,17.08.2026 20:00,Обычная,Локальные работы,'
    result = parse(header, row)

    assert result.errors == []
    assert result.rows[0]["address"] == "ул. Ленина, 1"


def test_time_with_explicit_timezone_is_kept():
    # оба конца окна в UTC: если заменить только начало, конец «20:00 по Москве» = 17:00 UTC
    # окажется раньше начала
    row = GOOD_ROW.replace("17.08.2026 18:00", "2026-08-17T18:00:00+00:00").replace(
        "17.08.2026 20:00", "2026-08-17T20:00:00+00:00"
    )
    result = parse(HEADER, row)

    assert result.errors == []
    assert result.rows[0]["window_start"].astimezone(UTC).hour == 18


def test_missing_required_columns():
    result = parse("id;адрес", "1;ул. Ленина")

    assert result.rows == []
    assert "широта" in result.errors[0]


def test_bad_row_reported_with_line_number_and_skipped():
    bad_row = "103;;95;37.658;60;17.08.2026 18:00;17.08.2026 20:00;Обычная;Локальные работы;"
    result = parse(HEADER, GOOD_ROW, bad_row)

    assert [row["id"] for row in result.rows] == [101]
    assert "строка 3: не заполнено поле «адрес»" in result.errors
    assert any(error.startswith("строка 3: поле «широта»") for error in result.errors)


def test_unknown_reference_lists_allowed_values():
    result = parse(HEADER, GOOD_ROW.replace("Срочная", "Очень срочная"))

    assert result.rows == []
    assert "Допустимо: Обычная, Срочная" in result.errors[0]


def test_window_end_must_be_after_start():
    result = parse(HEADER, GOOD_ROW.replace("17.08.2026 20:00", "17.08.2026 17:00"))

    assert result.errors == ["строка 2: «окно_конец» должно быть позже, чем «окно_начало»"]


def test_same_id_twice_in_file():
    result = parse(HEADER, GOOD_ROW, GOOD_ROW)

    assert len(result.rows) == 1
    assert result.errors == ["строка 3: заявка №101 уже есть в строке 2"]


def test_blank_lines_are_skipped():
    result = parse(HEADER, "", GOOD_ROW, ";;;;;;;;;")

    assert result.errors == []
    assert len(result.rows) == 1


def test_active_column():
    header = HEADER + ";активна"
    result = parse(
        header,
        GOOD_ROW + ";нет",
        GOOD_ROW.replace("101", "102") + ";Да",
        GOOD_ROW.replace("101", "103") + ";",
    )

    assert result.errors == []
    assert [row["is_active"] for row in result.rows] == [False, True, None]


def test_active_column_is_optional():
    result = parse(HEADER, GOOD_ROW)

    assert result.errors == []
    assert (
        result.rows[0]["is_active"] is None
    )  # сервис решит: новая — активна, старая — без изменений


def test_bad_active_value():
    result = parse(HEADER + ";активна", GOOD_ROW + ";может быть")

    assert result.errors == ["строка 2: «может быть» в поле «активна» — укажите «да» или «нет»"]


def test_empty_file():
    result = parse_requests_csv(b"", REFERENCES, MOSCOW)

    assert result.errors == ["файл пустой"]


WORK_TYPE_HEADER = (
    "адрес;широта;долгота;тип_работ;длительность_мин;окно_начало;окно_конец;приоритет;навык"
)


def test_work_type_fills_duration_and_skill():
    result = parse(
        WORK_TYPE_HEADER,
        "ул. Ленина, 1;55.74;37.658;Авария на ТКД;;17.08.2026 10:00;17.08.2026 12:00;Срочная;",
    )

    assert result.errors == []
    row = result.rows[0]
    assert (row["work_type_id"], row["duration_minutes"], row["skill_id"]) == (2, 80, 3)


def test_own_duration_wins_but_skill_follows_work_type():
    """Длительность можно задать свою, а навык определяется типом работ."""
    result = parse(
        WORK_TYPE_HEADER,
        "ул. Ленина, 1;55.74;37.658;Авария на ТКД;25;17.08.2026 10:00;17.08.2026 12:00;Срочная;Локальные работы",
    )

    assert result.errors == []
    row = result.rows[0]
    assert (row["work_type_id"], row["duration_minutes"], row["skill_id"]) == (2, 25, 3)


def test_without_work_type_duration_and_skill_are_required():
    result = parse(
        WORK_TYPE_HEADER,
        "ул. Ленина, 1;55.74;37.658;;;17.08.2026 10:00;17.08.2026 12:00;Срочная;",
    )

    assert result.rows == []
    assert any(
        "длительность_мин" in message and "тип_работ" in message for message in result.errors
    )
    assert any("навык" in message and "тип_работ" in message for message in result.errors)


def test_day_copy_moves_dates_and_drops_numbers():
    """Слепок дня, загруженный в другой день: время суток то же, номера новые."""
    from datetime import date, datetime, timedelta
    from datetime import timezone as tz

    from src.services.requests.requests_service import copy_rows_to_day

    moscow = tz(timedelta(hours=3))
    rows = [
        {
            "id": 74198,
            "window_start": datetime(2026, 8, 17, 20, 0, tzinfo=moscow),
            "window_end": datetime(2026, 8, 18, 2, 0, tzinfo=moscow),  # окно через полночь
        }
    ]

    copy_rows_to_day(rows, date(2026, 9, 20))

    row = rows[0]
    assert row["id"] is None
    assert row["window_start"].astimezone(moscow).strftime("%d.%m.%Y %H:%M") == "20.09.2026 20:00"
    assert row["window_end"].astimezone(moscow).strftime("%d.%m.%Y %H:%M") == "21.09.2026 02:00"
