"""Разбор и сборка CSV с исполнителями: слепок смен одного дня.

Формат файла (шаблон отдаёт GET /api/v1/engineers/csv-template):

    id;имя;широта_старта;долгота_старта;транспорт;навыки;смена_начало;смена_конец

- разделитель «;»; подойдут также «,» и табуляция — определяется по строке заголовка;
- «навыки» — от одного до трёх названий или номеров через запятую («Локальные работы, 3»);
- транспорт — названием из справочника (регистр не важен) или номером;
- id можно не заполнять — номер присвоится сам; если заполнен и такой исполнитель есть,
  он будет обновлён;
- время — «17.08.2026 09:00» или «2026-08-17T09:00»; без часового пояса считается московским.

Разбор строк, чисел, справочников и времени переиспользуется из CSV заявок: формат колонок
и правила у файлов одинаковые.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

from src.services.requests.requests_csv import (
    CsvParseResult,
    ReferenceOptions,
    cell,
    decode_file,
    detect_delimiter,
    is_blank_row,
    normalize_column_name,
    parse_datetime,
    parse_number,
    parse_reference,
    parse_request_id,
)

COLUMNS = [
    "id",
    "имя",
    "широта_старта",
    "долгота_старта",
    "транспорт",
    "навыки",
    "смена_начало",
    "смена_конец",
]
OPTIONAL_COLUMNS = {"id"}

MAX_SKILLS = 3


@dataclass
class EngineerReferenceLookup:
    transports: ReferenceOptions
    skills: ReferenceOptions


@dataclass
class EngineerCsvParseResult(CsvParseResult):
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_csv_template() -> str:
    """Текст шаблона: заголовок и две строки-примера (с номером и без)."""
    lines = [
        ";".join(COLUMNS),
        ";Бригада Соколов;55.7400;37.6580;Автомобиль;Локальные работы, Аварийные работы;"
        "17.08.2026 09:00;17.08.2026 18:00",
        "42;Бригада Мельников;55.7090;37.7368;Пешеход;Работы на подключение и дозаказы;"
        "17.08.2026 10:00;17.08.2026 21:00",
    ]
    return "\n".join(lines) + "\n"


def build_engineers_csv(rows: list[dict]) -> str:
    """Готовые строки исполнителей -> текст CSV с теми же колонками, что понимает загрузка."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=COLUMNS, delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def parse_engineers_csv(
    content: bytes, references: EngineerReferenceLookup, local_timezone: tzinfo
) -> EngineerCsvParseResult:
    """Разбирает файл целиком. Правильные строки попадают в rows, ошибки — в errors."""
    text_content = decode_file(content)
    if not text_content.strip():
        return EngineerCsvParseResult(errors=["файл пустой"])

    header_line = text_content.splitlines()[0]
    reader = csv.DictReader(io.StringIO(text_content), delimiter=detect_delimiter(header_line))
    reader.fieldnames = [normalize_column_name(name) for name in reader.fieldnames or []]

    missing_columns = [
        column
        for column in COLUMNS
        if column not in OPTIONAL_COLUMNS and column not in reader.fieldnames
    ]
    if missing_columns:
        return EngineerCsvParseResult(
            errors=[
                f"в файле нет колонок: {', '.join(missing_columns)}. "
                "Скачайте шаблон — в нём есть все нужные колонки"
            ]
        )

    result = EngineerCsvParseResult()
    line_by_engineer_id: dict[int, int] = {}

    for raw_row in reader:
        line_number = reader.line_num
        if is_blank_row(raw_row):
            continue

        row_errors: list[str] = []
        fields = parse_row(raw_row, references, local_timezone, row_errors)

        engineer_id = fields["id"]
        if engineer_id is not None:
            if engineer_id in line_by_engineer_id:
                row_errors.append(
                    f"исполнитель №{engineer_id} уже есть в строке {line_by_engineer_id[engineer_id]}"
                )
            else:
                line_by_engineer_id[engineer_id] = line_number

        if row_errors:
            result.errors.extend(f"строка {line_number}: {message}" for message in row_errors)
        else:
            result.rows.append(fields)

    return result


def parse_row(
    raw_row: dict, references: EngineerReferenceLookup, local_timezone: tzinfo, errors: list[str]
) -> dict:
    """Превращает одну строку файла в поля исполнителя; проблемы дописывает в errors."""
    engineer_id = parse_request_id(cell(raw_row, "id"), errors)

    name = cell(raw_row, "имя")
    if not name:
        errors.append("не заполнено поле «имя»")

    latitude = parse_number(cell(raw_row, "широта_старта"), "широта_старта", -90, 90, errors)
    longitude = parse_number(cell(raw_row, "долгота_старта"), "долгота_старта", -180, 180, errors)
    transport_id = parse_reference(
        cell(raw_row, "транспорт"), "транспорт", references.transports, errors, required=True
    )
    skill_ids = parse_skills(cell(raw_row, "навыки"), references.skills, errors)

    shift_start = parse_datetime(
        cell(raw_row, "смена_начало"), "смена_начало", local_timezone, errors
    )
    shift_end = parse_datetime(cell(raw_row, "смена_конец"), "смена_конец", local_timezone, errors)
    if shift_start and shift_end and shift_end <= shift_start:
        errors.append("«смена_конец» должна быть позже, чем «смена_начало»")

    return {
        "id": engineer_id,
        "name": name,
        "start_latitude": latitude,
        "start_longitude": longitude,
        "transport_id": transport_id,
        "skill_ids": skill_ids,
        "shift_start": shift_start,
        "shift_end": shift_end,
    }


def parse_skills(raw_value: str, skills: ReferenceOptions, errors: list[str]) -> list[int]:
    """«Локальные работы, 3» -> [1, 3]: от одного до трёх навыков без повторов (ТЗ)."""
    names = [part.strip() for part in raw_value.split(",") if part.strip()]
    if not names:
        errors.append("не заполнено поле «навыки»: нужен хотя бы один навык")
        return []

    skill_ids: list[int] = []
    for name in names:
        skill_id = parse_reference(name, "навыки", skills, errors, required=True)
        if skill_id is None:
            continue
        if skill_id in skill_ids:
            errors.append(f"навык «{name}» указан дважды")
            continue
        skill_ids.append(skill_id)

    if len(skill_ids) > MAX_SKILLS:
        errors.append(f"навыков не должно быть больше {MAX_SKILLS}")
    return skill_ids


def format_datetime(moment: datetime, local_timezone: tzinfo) -> str:
    """Момент времени -> «17.08.2026 09:00» по местному времени — как в шаблоне."""
    return moment.astimezone(local_timezone).strftime("%d.%m.%Y %H:%M")
