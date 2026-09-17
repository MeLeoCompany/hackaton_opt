"""Разбор CSV-файла с заявками, который загружает диспетчер.

Формат файла (шаблон отдаёт GET /api/v1/requests/csv-template):

    id;адрес;широта;долгота;тип_работ;длительность_мин;окно_начало;окно_конец;приоритет;навык;транспорт;активна

- разделитель «;»; подойдут также «,» и табуляция — определяется по строке заголовка;
- «тип_работ» — из справочника нормативов; он задаёт нужный навык, а «длительность_мин»
  можно не заполнять: возьмётся норматив работы на месте. Колонка «навык» нужна только
  строкам без типа работ;
- «активна» — «да» или «нет» (учитывать ли заявку при планировании). Колонку можно не
  добавлять или оставить пустой: новая заявка станет активной, у существующей флаг не изменится;
- кодировка UTF-8 или Windows-1251 (так сохраняет Excel);
- id можно не заполнять — номер присвоится сам; если заполнен и такая заявка уже есть,
  она будет обновлена;
- приоритет, навык и транспорт — названием из справочника (регистр не важен) или номером;
  транспорт можно оставить пустым;
- время — «17.08.2026 10:00» или «2026-08-17T10:00»; без часового пояса считается московским.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

COLUMNS = [
    "id",
    "адрес",
    "широта",
    "долгота",
    "тип_работ",
    "длительность_мин",
    "окно_начало",
    "окно_конец",
    "приоритет",
    "навык",
    "транспорт",
    "активна",
]
# «длительность_мин» и «навык» необязательны, если указан «тип_работ»
OPTIONAL_COLUMNS = {"id", "тип_работ", "длительность_мин", "навык", "транспорт", "активна"}

DATETIME_FORMATS = ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S")

ACTIVE_WORDS = {"да", "1", "true", "yes", "вкл", "активна"}
INACTIVE_WORDS = {"нет", "0", "false", "no", "выкл", "выключена"}


@dataclass
class ReferenceOptions:
    """Значения одного справочника: по названию или номеру находим номер записи в БД."""

    id_by_key: dict[str, int]
    names: list[str]


@dataclass
class WorkTypeNorm:
    """Нормативы типа работ: чем заполнить пустые «длительность_мин» и «навык»."""

    skill_id: int
    work_minutes: int


@dataclass
class ReferenceLookup:
    skills: ReferenceOptions
    priorities: ReferenceOptions
    transports: ReferenceOptions
    work_types: ReferenceOptions
    work_type_norms: dict[int, WorkTypeNorm]


@dataclass
class CsvParseResult:
    rows: list[dict] = field(default_factory=list)  # готовые поля заявок из правильных строк
    errors: list[str] = field(default_factory=list)  # "строка 5: не заполнен адрес"


def reference_options(items: list[tuple[int, str]]) -> ReferenceOptions:
    """Собирает справочник для поиска из пар (номер, название)."""
    id_by_key = {}
    for item_id, name in items:
        id_by_key[name.strip().lower()] = item_id
        id_by_key[str(item_id)] = item_id
    return ReferenceOptions(id_by_key=id_by_key, names=[name for _, name in items])


def build_csv_template() -> str:
    """Текст шаблона: заголовок и две строки-примера (с номером и без)."""
    lines = [
        ";".join(COLUMNS),
        # длительность и навык не заполнены: возьмутся из типа работ
        ";Город Москва, пер.Маяковского, д. 2;55.7400;37.6580;Подключение клиентов, базовая;;"
        "17.08.2026 18:00;17.08.2026 20:00;Обычная;;;да",
        "400000001;Город Москва, ул.Саратовская, д. 16;55.7090;37.7368;Авария на ТКД;90;"
        "17.08.2026 20:00;17.08.2026 22:00;Срочная;Аварийные работы;Автомобиль;нет",
    ]
    return "\n".join(lines) + "\n"


def format_datetime(moment: datetime, local_timezone: tzinfo) -> str:
    """Момент времени -> «17.08.2026 18:00» по местному времени — как в шаблоне."""
    return moment.astimezone(local_timezone).strftime("%d.%m.%Y %H:%M")


def build_requests_csv(rows: list[dict]) -> str:
    """Готовые строки заявок -> текст CSV с теми же колонками, что понимает загрузка.

    Выгруженный файл можно загрузить обратно — тем же днём или в другой день.
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=COLUMNS, delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def parse_requests_csv(
    content: bytes, references: ReferenceLookup, local_timezone: tzinfo
) -> CsvParseResult:
    """Разбирает файл целиком. Правильные строки попадают в rows, ошибки — в errors.

    Строка с ошибкой в rows не попадает. Пустые строки пропускаются.
    """
    text_content = decode_file(content)
    if not text_content.strip():
        return CsvParseResult(errors=["файл пустой"])

    header_line = text_content.splitlines()[0]
    reader = csv.DictReader(io.StringIO(text_content), delimiter=detect_delimiter(header_line))
    reader.fieldnames = [normalize_column_name(name) for name in reader.fieldnames or []]

    missing_columns = [
        column
        for column in COLUMNS
        if column not in OPTIONAL_COLUMNS and column not in reader.fieldnames
    ]
    if missing_columns:
        return CsvParseResult(
            errors=[
                f"в файле нет колонок: {', '.join(missing_columns)}. "
                "Скачайте шаблон — в нём есть все нужные колонки"
            ]
        )

    result = CsvParseResult()
    line_by_request_id: dict[int, int] = {}

    for raw_row in reader:
        line_number = reader.line_num
        if is_blank_row(raw_row):
            continue

        row_errors: list[str] = []
        fields = parse_row(raw_row, references, local_timezone, row_errors)

        request_id = fields["id"]
        if request_id is not None:
            if request_id in line_by_request_id:
                row_errors.append(
                    f"заявка №{request_id} уже есть в строке {line_by_request_id[request_id]}"
                )
            else:
                line_by_request_id[request_id] = line_number

        if row_errors:
            result.errors.extend(f"строка {line_number}: {message}" for message in row_errors)
        else:
            result.rows.append(fields)

    return result


def decode_file(content: bytes) -> str:
    """UTF-8 (в том числе с BOM, как сохраняет Excel), иначе Windows-1251."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1251", errors="replace")


def detect_delimiter(header_line: str) -> str:
    """Разделитель — тот символ из «;», «,» и табуляции, которого в заголовке больше всего."""
    return max([";", ",", "\t"], key=header_line.count)


def normalize_column_name(name: str) -> str:
    """« Окно начало » -> «окно_начало»: без пробелов по краям, строчные, пробелы -> «_»."""
    return name.replace("﻿", "").strip().lower().replace(" ", "_")


def is_blank_row(raw_row: dict) -> bool:
    return all(not value.strip() for value in raw_row.values() if isinstance(value, str))


def cell(raw_row: dict, column: str) -> str:
    return (raw_row.get(column) or "").strip()


def parse_row(
    raw_row: dict, references: ReferenceLookup, local_timezone: tzinfo, errors: list[str]
) -> dict:
    """Превращает одну строку файла в поля заявки; найденные проблемы дописывает в errors."""
    request_id = parse_request_id(cell(raw_row, "id"), errors)

    address = cell(raw_row, "адрес")
    if not address:
        errors.append("не заполнено поле «адрес»")

    latitude = parse_number(cell(raw_row, "широта"), "широта", -90, 90, errors)
    longitude = parse_number(cell(raw_row, "долгота"), "долгота", -180, 180, errors)

    work_type_id = parse_reference(
        cell(raw_row, "тип_работ"), "тип_работ", references.work_types, errors, required=False
    )
    duration_minutes = parse_duration(cell(raw_row, "длительность_мин"), errors)

    window_start = parse_datetime(
        cell(raw_row, "окно_начало"), "окно_начало", local_timezone, errors
    )
    window_end = parse_datetime(cell(raw_row, "окно_конец"), "окно_конец", local_timezone, errors)
    if window_start and window_end and window_end <= window_start:
        errors.append("«окно_конец» должно быть позже, чем «окно_начало»")

    priority_id = parse_reference(
        cell(raw_row, "приоритет"), "приоритет", references.priorities, errors, required=True
    )
    skill_id = parse_reference(
        cell(raw_row, "навык"), "навык", references.skills, errors, required=False
    )

    # навык определяется типом работ, длительность берётся из норматива, если её не задали
    norm = references.work_type_norms.get(work_type_id) if work_type_id is not None else None
    if norm is not None:
        skill_id = norm.skill_id
        duration_minutes = norm.work_minutes if duration_minutes is None else duration_minutes
    if duration_minutes is None:
        errors.append(
            "не заполнено поле «длительность_мин» — заполните его или укажите «тип_работ»"
        )
    if skill_id is None:
        errors.append("не заполнено поле «навык» — заполните его или укажите «тип_работ»")
    transport_id = parse_reference(
        cell(raw_row, "транспорт"), "транспорт", references.transports, errors, required=False
    )
    is_active = parse_active(cell(raw_row, "активна"), errors)

    return {
        "id": request_id,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "duration_minutes": duration_minutes,
        "window_start": window_start,
        "window_end": window_end,
        "priority_id": priority_id,
        "skill_id": skill_id,
        "transport_id": transport_id,
        "work_type_id": work_type_id,
        "is_active": is_active,
    }


def parse_active(raw_value: str, errors: list[str]) -> bool | None:
    """«да» / «нет» -> True / False; пусто -> None (решает сервис: новая — активна, старая — без изменений)."""
    if not raw_value:
        return None
    normalized = raw_value.strip().lower()
    if normalized in ACTIVE_WORDS:
        return True
    if normalized in INACTIVE_WORDS:
        return False
    errors.append(f"«{raw_value}» в поле «активна» — укажите «да» или «нет»")
    return None


def parse_request_id(raw_value: str, errors: list[str]) -> int | None:
    if not raw_value:
        return None
    if raw_value.isdigit() and int(raw_value) > 0:
        return int(raw_value)
    errors.append(f"номер заявки «{raw_value}» должен быть целым положительным числом")
    return None


def parse_number(
    raw_value: str, column: str, minimum: float, maximum: float, errors: list[str]
) -> float | None:
    """Число с точкой или запятой (55.74 или 55,74) в пределах от minimum до maximum."""
    if not raw_value:
        errors.append(f"не заполнено поле «{column}»")
        return None
    try:
        value = float(raw_value.replace(",", "."))
    except ValueError:
        errors.append(f"«{raw_value}» в поле «{column}» — не число")
        return None
    if not minimum <= value <= maximum:
        errors.append(
            f"поле «{column}» должно быть от {minimum} до {maximum}, а в файле {raw_value}"
        )
        return None
    return value


def parse_duration(raw_value: str, errors: list[str]) -> int | None:
    """Пусто — не ошибка: длительность может прийти из нормативов типа работ."""
    if not raw_value:
        return None
    if raw_value.isdigit() and int(raw_value) > 0:
        return int(raw_value)
    errors.append(
        f"«{raw_value}» в поле «длительность_мин» — должно быть целое число минут больше нуля"
    )
    return None


def parse_datetime(
    raw_value: str, column: str, local_timezone: tzinfo, errors: list[str]
) -> datetime | None:
    """Дата и время; если часовой пояс не указан, время считается местным (московским)."""
    if not raw_value:
        errors.append(f"не заполнено поле «{column}»")
        return None

    moment = None
    try:
        moment = datetime.fromisoformat(raw_value)
    except ValueError:
        for date_format in DATETIME_FORMATS:
            try:
                # Часовой пояс добавляется ниже из настройки локального времени.
                moment = datetime.strptime(raw_value, date_format)  # noqa: DTZ007
                break
            except ValueError:
                continue

    if moment is None:
        errors.append(
            f"«{raw_value}» в поле «{column}» не похоже на дату и время, пример: 17.08.2026 10:00"
        )
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=local_timezone)
    return moment


def parse_reference(
    raw_value: str, column: str, options: ReferenceOptions, errors: list[str], required: bool
) -> int | None:
    """Значение справочника по названию или номеру."""
    if not raw_value:
        if required:
            errors.append(f"не заполнено поле «{column}»")
        return None
    reference_id = options.id_by_key.get(raw_value.strip().lower())
    if reference_id is None:
        errors.append(
            f"в поле «{column}» неизвестное значение «{raw_value}». Допустимо: {', '.join(options.names)}"
        )
    return reference_id
