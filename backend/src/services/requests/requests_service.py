"""Заявки: просмотр, создание, изменение, удаление и загрузка из CSV."""

from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DataError, InUseError, NotFoundError
from src.core.free_id import smallest_free_id
from src.core.local_day import day_bounds, local_timezone
from src.models import Office, Request, RequestStatus, RequestStatusId
from src.repositories.references import references_repository
from src.repositories.request_statuses import request_statuses_repository
from src.repositories.requests import requests_repository
from src.schemas.bulk import BulkDeleteProblem, BulkDeleteReport, BulkUpdateReport
from src.schemas.requests import (
    CancelledTransfer,
    RequestActivityReport,
    RequestBulkUpdate,
    RequestCreate,
    RequestImportReport,
    RequestStatusHistoryItem,
    RequestWrite,
)
from src.services.requests import request_status_service
from src.services.requests.requests_csv import (
    ReferenceLookup,
    WorkTypeNorm,
    build_requests_csv,
    format_datetime,
    parse_requests_csv,
    reference_options,
)


class RequestNotFoundError(NotFoundError):
    """Заявки с таким номером нет."""


class RequestInUseError(InUseError):
    """Заявку нельзя удалить: на неё ссылаются планы или события перепланирования."""


class RequestDataError(DataError):
    """Данные заявки не прошли проверку."""


async def list_requests(
    session: AsyncSession,
    office_id: int,
    plan_date: date | None = None,
    *,
    with_moved_out: bool = True,
) -> list[Request]:
    """Все заявки офиса или только те, чьё окно попадает в выбранный день.

    with_moved_out — оставлять ли в дне заявки, перенесённые с него в другой день. Списку
    оператора они нужны, слепку дня в CSV — нет: там день описывается своими окнами.
    """
    if plan_date is None:
        return await requests_repository.list_requests(session, office_id=office_id)
    day_start, day_end = day_bounds(plan_date)
    requests = await requests_repository.list_requests_in_period(
        session, day_start, day_end, office_id=office_id
    )
    if not with_moved_out:
        return requests
    # перенесённые с этого дня оставляем в списке: иначе заявка молча исчезает из дня,
    # в котором её ждали, и оператору негде увидеть, куда она делась
    moved = await requests_repository.list_requests_moved_from(
        session, plan_date, office_id=office_id
    )
    known = {request.id for request in requests}
    requests.extend(request for request in moved if request.id not in known)
    requests.sort(key=lambda request: (request.window_start, request.id))
    return requests


async def get_request(session: AsyncSession, request_id: int, office_id: int) -> Request:
    """Заявка офиса. Чужая выглядит как несуществующая: о заявках других офисов не сообщаем."""
    request = await requests_repository.get_request(session, request_id)
    if request is None or request.office_id != office_id:
        raise RequestNotFoundError(f"Заявка №{request_id} не найдена")
    return request


def not_editable_reason(request: Request) -> str | None:
    """Почему заявку менять нельзя; None — можно.

    Менять можно только «Новую»: заявка в плане, в работе или выполненная — часть плана, её
    правка тихо разошлась бы с маршрутами бригад. Отменённую не правят, а копируют в новую.
    """
    if request.status_id == RequestStatusId.NEW:
        return None
    status_name = request.status.name if request.status is not None else "не «Новая»"
    advice = (
        "сделайте её копию — копия будет новой, её можно править"
        if request.status_id == RequestStatusId.CANCELLED
        else "менять её нельзя, чтобы не разойтись с планом"
    )
    return f"заявка №{request.id} уже «{status_name}»: {advice}"


async def create_request(
    session: AsyncSession,
    payload: RequestCreate,
    office_id: int,
    user_id: int | None = None,
    comment: str = "Заявка создана",
) -> Request:
    await requests_repository.lock_request_ids(session)
    await check_references_exist(session, payload)
    await apply_work_type_norms(session, payload)

    taken = (
        await requests_repository.get_request(session, payload.id)
        if payload.id is not None
        else None
    )
    if taken is not None:
        raise RequestDataError(
            [
                f"номер №{payload.id} уже занят заявкой"
                f"{await elsewhere(session, taken.office_id, office_id)}. Номера общие для всех "
                "офисов — оставьте поле пустым, и номер подберётся сам"
            ]
        )

    fields = {**payload.model_dump(exclude={"equipment"}), "office_id": office_id}
    if fields["id"] is None:
        fields["id"] = smallest_free_id(await requests_repository.list_request_ids(session))

    new_status = await session.get(RequestStatus, RequestStatusId.NEW)
    request = requests_repository.add_request(
        session, fields, equipment_quantities(payload), new_status
    )
    # заявка должна появиться в БД раньше записи истории, которая на неё ссылается
    await session.flush()
    request_statuses_repository.add_history(
        session,
        [request.id],
        None,
        RequestStatusId.NEW,
        manual=True,
        user_id=user_id,
        comment=comment,
    )
    await session.flush()
    await session.commit()
    return request


async def update_request(
    session: AsyncSession, request_id: int, payload: RequestWrite, office_id: int
) -> Request:
    request = await get_request(session, request_id, office_id)
    reason = not_editable_reason(request)
    if reason is not None:
        raise RequestDataError([reason])
    await check_references_exist(session, payload)
    await apply_work_type_norms(session, payload)
    requests_repository.apply_changes(
        request, payload.model_dump(exclude={"equipment"}), equipment_quantities(payload)
    )
    await session.commit()
    return request


async def duplicate_request(
    session: AsyncSession,
    request_id: int,
    office_id: int,
    user_id: int | None = None,
    plan_date: date | None = None,
) -> Request:
    """Копия отменённой заявки: новая заявка с теми же адресом, окном и работами.

    Отмена окончательна — в «Новая» отменённую не возвращают. Если работу всё же нужно
    сделать, оператор копирует заявку: копия «Новая», её можно поправить и спланировать.
    plan_date — перенести копию на другой день: время суток окна то же, дата новая.
    """
    source = await get_request(session, request_id, office_id)
    if source.status_id != RequestStatusId.CANCELLED:
        raise RequestDataError(
            [f"копировать можно только отменённую заявку, а №{request_id} — «{source.status.name}»"]
        )
    window_start, window_end = source.window_start, source.window_end
    if plan_date is not None:
        timezone = local_timezone()
        day_offset = (
            window_end.astimezone(timezone).date() - window_start.astimezone(timezone).date()
        ).days
        window_start = moved_to_day(window_start, plan_date, 0)
        window_end = moved_to_day(window_end, plan_date, day_offset)
    payload = RequestCreate(
        address=source.address,
        latitude=float(source.latitude),
        longitude=float(source.longitude),
        duration_minutes=source.duration_minutes,
        window_start=window_start,
        window_end=window_end,
        priority_id=source.priority_id,
        skill_id=source.skill_id,
        transport_id=source.transport_id,
        work_type_id=source.work_type_id,
        equipment=[
            {"equipment_id": item.equipment_id, "quantity": item.quantity}
            for item in source.equipment
        ],
    )
    moved = f" с переносом на {plan_date.strftime('%d.%m.%Y')}" if plan_date is not None else ""
    return await create_request(
        session,
        payload,
        office_id,
        user_id,
        comment=f"Копия отменённой заявки №{request_id}{moved}",
    )


async def delete_request(session: AsyncSession, request_id: int, office_id: int) -> None:
    """Удалить можно только «Новую» заявку.

    Всё остальное — след работы: заявка в плане стоит в маршруте бригады, начатую и
    выполненную нельзя терять, отменённая объясняет, почему работу не сделали. Такие заявки
    отменяют, а не удаляют.
    """
    request = await get_request(session, request_id, office_id)
    if request.status_id != RequestStatusId.NEW:
        raise RequestInUseError(
            f"Заявку №{request_id} нельзя удалить: она «{request.status.name}». "
            "Удалять можно только «Новые»; ненужную работу отмените"
        )

    assignments, events = await requests_repository.count_request_usages(session, request_id)
    if assignments or events:
        raise RequestInUseError(
            f"Заявку №{request_id} нельзя удалить: она используется в планах ({assignments}) "
            f"и событиях перепланирования ({events})"
        )

    await requests_repository.delete_request(session, request)
    await session.commit()


async def delete_requests(
    session: AsyncSession, request_ids: list[int], office_id: int
) -> BulkDeleteReport:
    """Удаляет выбранные заявки: те, что можно, — остальные возвращает с причинами.

    Оператор отмечает галочками десятки строк, и одна заявка в плане не должна отменять
    удаление всех прочих: удаляем что получается, а по остальным объясняем почему.
    """
    problems = []
    deleted = 0
    for request_id in dict.fromkeys(request_ids):
        try:
            await delete_request(session, request_id, office_id)
            deleted += 1
        except (RequestNotFoundError, RequestInUseError) as error:
            problems.append(BulkDeleteProblem(id=request_id, reason=str(error)))
    return BulkDeleteReport(deleted=deleted, problems=problems)


async def update_requests(
    session: AsyncSession,
    payload: RequestBulkUpdate,
    office_id: int,
    user_id: int | None = None,
) -> BulkUpdateReport:
    """Групповая правка: меняет у выбранных заявок только отмеченные оператором поля.

    Либо меняются все заявки, либо ни одна: если хоть одну править нельзя или окно после
    правки развалится, оператор сначала узнаёт об этом, а данные остаются как были.
    Статус — не поле, а переход: его можно сменить и у заявки, которую править нельзя.
    """
    unique_ids = list(dict.fromkeys(payload.request_ids))
    stored = await requests_repository.get_requests_by_ids(session, unique_ids)
    requests = [request for request in stored.values() if request.office_id == office_id]
    missing = [
        request_id for request_id in unique_ids if request_id not in {r.id for r in requests}
    ]
    if missing:
        listed = ", ".join(f"№{request_id}" for request_id in missing)
        raise RequestNotFoundError(f"Не найдены заявки: {listed}")

    changes = payload.changes()
    # меняем только статус — заявке в плане это разрешено, правка полей ей запрещена
    if changes or payload.move_to_day is not None:
        blocked = [reason for request in requests if (reason := not_editable_reason(request))]
        if blocked:
            raise RequestDataError(blocked)

    await check_bulk_references(session, changes)
    if changes.get("work_type_id") is not None:
        changes = await with_work_type_norms(session, changes)

    problems = []
    for request in requests:
        window = new_window(request, changes, payload.move_to_day)
        if window["window_end"] <= window["window_start"]:
            problems.append(
                f"заявка №{request.id}: конец окна должен быть позже начала "
                f"({local_period(window)})"
            )
    if problems:
        raise RequestDataError(problems)

    for request in requests:
        window = new_window(request, changes, payload.move_to_day)
        requests_repository.apply_changes(request, {**changes, **window})
    if payload.status_id is not None:
        await request_status_service.change_status(
            session, requests, payload.status_id, manual=True, user_id=user_id
        )
    await session.commit()
    return BulkUpdateReport(updated=len(requests))


def new_window(request: Request, changes: dict, move_to_day: date | None) -> dict:
    """Окно заявки после правки: что задали явно, что сдвинули на другой день, что было."""
    timezone = local_timezone()
    window = {
        "window_start": changes.get("window_start") or request.window_start,
        "window_end": changes.get("window_end") or request.window_end,
    }
    if move_to_day is not None:
        # день другой, время суток то же: длина окна и часы работы сохраняются
        window = {
            name: moment.astimezone(timezone).replace(
                year=move_to_day.year, month=move_to_day.month, day=move_to_day.day
            )
            for name, moment in window.items()
        }
        if window["window_end"] <= window["window_start"]:
            window["window_end"] += timedelta(days=1)  # окно через полночь остаётся ночным
    return window


def local_period(window: dict) -> str:
    timezone = local_timezone()
    start = window["window_start"].astimezone(timezone)
    end = window["window_end"].astimezone(timezone)
    return f"{start:%d.%m %H:%M}–{end:%d.%m %H:%M}"


async def check_bulk_references(session: AsyncSession, changes: dict) -> None:
    """Те же справочники, что и у одной заявки, но проверяем только заданные поля."""
    references = await load_reference_lookup(session)
    catalogues = {
        "priority_id": (references.priorities, "приоритета"),
        "skill_id": (references.skills, "навыка"),
        "work_type_id": (references.work_types, "типа работ"),
        "transport_id": (references.transports, "транспорта"),
    }
    problems = [
        f"{title} №{changes[field]} нет в справочнике"
        for field, (catalogue, title) in catalogues.items()
        if changes.get(field) is not None and str(changes[field]) not in catalogue.id_by_key
    ]
    if problems:
        raise RequestDataError(problems)


async def with_work_type_norms(session: AsyncSession, changes: dict) -> dict:
    """Тип работ задаёт навык и, если длительность не указали, её норматив."""
    references = await load_reference_lookup(session)
    norm = references.work_type_norms.get(changes["work_type_id"])
    if norm is None:
        return changes
    filled = {**changes, "skill_id": norm.skill_id}
    if filled.get("duration_minutes") is None:
        filled["duration_minutes"] = norm.work_minutes
    return filled


async def set_requests_active(
    session: AsyncSession,
    request_ids: list[int],
    is_active: bool,
    office_id: int,
    user_id: int | None = None,
) -> RequestActivityReport:
    """Прежний переключатель «активна»: включить — «Новая», выключить — «Отменена»."""
    return await set_requests_status(
        session,
        request_ids,
        RequestStatusId.NEW if is_active else RequestStatusId.CANCELLED,
        office_id,
        user_id,
    )


async def set_requests_status(
    session: AsyncSession,
    request_ids: list[int],
    status_id: int,
    office_id: int,
    user_id: int | None = None,
) -> RequestActivityReport:
    """Оператор переводит заявки офиса в статус — только ручными переходами из таблицы.

    Если хоть одной заявки нет или хоть одной переход запрещён — не меняется ничего.
    """
    unique_ids = list(dict.fromkeys(request_ids))
    existing_by_id = {
        request_id: request
        for request_id, request in (
            await requests_repository.get_requests_by_ids(session, unique_ids)
        ).items()
        if request.office_id == office_id
    }

    missing_ids = [request_id for request_id in unique_ids if request_id not in existing_by_id]
    if missing_ids:
        listed = ", ".join(f"№{request_id}" for request_id in missing_ids)
        raise RequestNotFoundError(f"Не найдены заявки: {listed}")

    await request_status_service.change_status(
        session, list(existing_by_id.values()), status_id, manual=True, user_id=user_id
    )
    await session.commit()
    return RequestActivityReport(updated=len(unique_ids))


async def get_request_history(
    session: AsyncSession, request_id: int, office_id: int
) -> list[RequestStatusHistoryItem]:
    """История статусов заявки офиса: что с ней происходило, кто и когда менял статус."""
    await get_request(session, request_id, office_id)
    return [
        RequestStatusHistoryItem(
            id=entry.id,
            changed_at=entry.changed_at,
            from_status_id=entry.from_status_id,
            to_status_id=entry.to_status_id,
            manual=entry.manual,
            user_name=user_name,
            plan_id=entry.plan_id,
            comment=entry.comment,
        )
        for entry, user_name in await request_statuses_repository.list_history(session, request_id)
    ]


async def export_requests_csv(
    session: AsyncSession, office_id: int, plan_date: date | None = None
) -> str:
    """Заявки офиса за день в CSV — слепок дня, который можно загрузить обратно или в другой день."""
    requests = await list_requests(session, office_id, plan_date, with_moved_out=False)
    references = await load_reference_names(session)
    timezone = local_timezone()
    return build_requests_csv(
        [
            {
                "id": request.id,
                "адрес": request.address,
                "широта": f"{float(request.latitude):.6f}",
                "долгота": f"{float(request.longitude):.6f}",
                "тип_работ": (
                    references["work_types"].get(request.work_type_id, "")
                    if request.work_type_id is not None
                    else ""
                ),
                "длительность_мин": request.duration_minutes,
                "окно_начало": format_datetime(request.window_start, timezone),
                "окно_конец": format_datetime(request.window_end, timezone),
                "приоритет": references["priorities"].get(request.priority_id, ""),
                "навык": references["skills"].get(request.skill_id, ""),
                "транспорт": (
                    references["transports"].get(request.transport_id, "")
                    if request.transport_id is not None
                    else ""
                ),
                "активна": "да" if request.is_active else "нет",
                "оборудование": ", ".join(
                    f"{references['equipment'].get(item.equipment_id, item.equipment_id)}: "
                    f"{item.quantity}"
                    for item in request.equipment
                ),
            }
            for request in requests
        ]
    )


async def load_reference_names(session: AsyncSession) -> dict[str, dict[int, str]]:
    """Названия справочников по номеру — для выгрузки в CSV."""
    return {
        "skills": {
            skill.id: skill.name for skill in await references_repository.list_skills(session)
        },
        "priorities": {
            priority.id: priority.name
            for priority in await references_repository.list_priorities(session)
        },
        "transports": {
            transport.id: transport.name
            for transport in await references_repository.list_transports(session)
        },
        "work_types": {
            work_type.id: work_type.name
            for work_type in await references_repository.list_work_types(session)
        },
        "equipment": {
            equipment.id: equipment.name
            for equipment in await references_repository.list_equipment(session)
        },
    }


def moved_to_day(moment: datetime, plan_date: date, day_offset: int) -> datetime:
    """Тот же час и минуты, но в выбранном дне (плюс day_offset суток для окон через полночь)."""
    local = moment.astimezone(local_timezone())
    return local.replace(year=plan_date.year, month=plan_date.month, day=plan_date.day) + timedelta(
        days=day_offset
    )


def transfer_cancelled_rows(
    rows: list[dict], cancelled: CancelledTransfer
) -> tuple[list[dict], int]:
    """Отменённые заявки при переносе дня: «активна: нет» — их отменили в том дне, не в этом.

    Возвращает строки для загрузки и сколько отменённых пропущено.
    """
    if cancelled is CancelledTransfer.SKIP:
        kept = [row for row in rows if row["is_active"] is not False]
        return kept, len(rows) - len(kept)
    for row in rows:
        if row["is_active"] is False:
            row["is_active"] = True
    return rows, 0


def copy_rows_to_day(rows: list[dict], plan_date: date) -> None:
    """Переносит разобранные строки в выбранный день: время суток то же, номера новые.

    Так слепок одного дня превращается в самостоятельную копию на другой день,
    а не перезаписывает исходные заявки.
    """
    timezone = local_timezone()
    for fields in rows:
        start, end = fields["window_start"], fields["window_end"]
        day_offset = (end.astimezone(timezone).date() - start.astimezone(timezone).date()).days
        fields["window_start"] = moved_to_day(start, plan_date, 0)
        fields["window_end"] = moved_to_day(end, plan_date, day_offset)
        fields["id"] = None


async def import_requests_csv(
    session: AsyncSession,
    content: bytes,
    office_id: int,
    plan_date: date | None = None,
    user_id: int | None = None,
    cancelled: CancelledTransfer = CancelledTransfer.AS_NEW,
) -> RequestImportReport:
    """Загружает заявки из CSV одной транзакцией.

    Если хоть одна строка с ошибкой — не сохраняется ничего, диспетчер получает список
    ошибок с номерами строк. Заявка с уже существующим номером обновляется, без номера
    или с новым номером — добавляется.

    Если указан plan_date, файл переносится в этот день копией: время суток сохраняется,
    даты заменяются, номера выдаются новые. cancelled — что делать с отменёнными заявками
    из файла: перенести «Новыми» или не переносить вовсе (в новом дне их никто не отменял).
    """
    await requests_repository.lock_request_ids(session)
    references = await load_reference_lookup(session)
    parsed = parse_requests_csv(content, references, local_timezone())
    if parsed.errors:
        raise RequestDataError(parsed.errors)
    if not parsed.rows:
        raise RequestDataError(["в файле нет ни одной заявки"])

    skipped_cancelled = 0
    if plan_date is not None:
        copy_rows_to_day(parsed.rows, plan_date)
        parsed.rows, skipped_cancelled = transfer_cancelled_rows(parsed.rows, cancelled)

    ids_in_file = [row["id"] for row in parsed.rows if row["id"] is not None]
    existing_by_id = await requests_repository.get_requests_by_ids(session, ids_in_file)
    # номер из файла совпал с заявкой другого офиса — не трогаем её и не пишем поверх
    foreign = sorted(
        request_id
        for request_id, request in existing_by_id.items()
        if request.office_id != office_id
    )
    if foreign:
        listed = ", ".join(f"№{request_id}" for request_id in foreign)
        raise RequestDataError(
            [f"заявки {listed} уже есть в другом офисе — уберите номера или укажите другие"]
        )

    # в плане, в работе, выполненные и отменённые файл не перезаписывает: менять можно
    # только «Новые» (см. not_editable_reason)
    locked = [
        reason
        for request in existing_by_id.values()
        if (reason := not_editable_reason(request)) is not None
    ]
    if locked:
        raise RequestDataError(sorted(locked))

    # номера строк без номера подбираем заранее: они не должны совпасть ни с занятыми
    # в БД, ни с явными номерами из файла, ни друг с другом
    taken_ids = await requests_repository.list_request_ids(session)
    taken_ids.update(ids_in_file)

    status_by_id = {
        status.id: status for status in await request_statuses_repository.list_statuses(session)
    }
    status_changes: list[tuple[Request, bool]] = []
    created_statuses: list[tuple[int, int]] = []  # (номер новой заявки, её начальный статус)
    created = 0
    updated = 0
    for fields in parsed.rows:
        existing_request = existing_by_id.get(fields["id"])
        fields_without_id = {name: value for name, value in fields.items() if name != "id"}
        # оборудование — отдельно; нет колонки в файле — у заявки его не трогаем
        equipment = fields_without_id.pop("equipment", None)

        # «активна» в файле — прежний флаг: «да» — «Новая», «нет» — «Отменена»
        is_active = fields_without_id.pop("is_active")

        if existing_request is not None:
            requests_repository.apply_changes(existing_request, fields_without_id, equipment)
            # не указана — статус не трогаем: иначе повторная загрузка файла молча вернула
            # бы в работу заявки, которые оператор отменил
            if is_active is not None:
                status_changes.append((existing_request, is_active))
            updated += 1
            continue

        fields_without_id["office_id"] = office_id
        identifier = fields["id"] if fields["id"] is not None else smallest_free_id(taken_ids)
        taken_ids.add(identifier)
        fields_without_id["id"] = identifier
        # новая заявка без указанной активности — «Новая»
        initial_status = RequestStatusId.CANCELLED if is_active is False else RequestStatusId.NEW
        requests_repository.add_request(
            session, fields_without_id, equipment, status_by_id[initial_status]
        )
        created_statuses.append((identifier, initial_status))
        created += 1

    # смена статуса существующих — по таблице переходов; запрещённый переход отменяет загрузку
    for is_active in (True, False):
        requests = [request for request, active in status_changes if active is is_active]
        if requests:
            await request_status_service.change_status(
                session,
                requests,
                RequestStatusId.NEW if is_active else RequestStatusId.CANCELLED,
                manual=True,
                user_id=user_id,
                comment="Загрузка CSV",
            )

    # новые заявки должны появиться в БД раньше записей истории, которые на них ссылаются
    await session.flush()
    for status_id in {status_id for _, status_id in created_statuses}:
        request_statuses_repository.add_history(
            session,
            [identifier for identifier, initial in created_statuses if initial == status_id],
            None,
            status_id,
            manual=True,
            user_id=user_id,
            comment="Заявка загружена из CSV",
        )
    await session.flush()
    await session.commit()
    return RequestImportReport(
        created=created, updated=updated, skipped_cancelled=skipped_cancelled
    )


async def load_reference_lookup(session: AsyncSession) -> ReferenceLookup:
    skills = await references_repository.list_skills(session)
    priorities = await references_repository.list_priorities(session)
    transports = await references_repository.list_transports(session)
    work_types = await references_repository.list_work_types(session)
    equipment = await references_repository.list_equipment(session)
    return ReferenceLookup(
        skills=reference_options([(skill.id, skill.name) for skill in skills]),
        priorities=reference_options([(priority.id, priority.name) for priority in priorities]),
        transports=reference_options([(transport.id, transport.name) for transport in transports]),
        work_types=reference_options([(work_type.id, work_type.name) for work_type in work_types]),
        equipment=reference_options([(item.id, item.name) for item in equipment]),
        work_type_norms={
            work_type.id: WorkTypeNorm(
                skill_id=work_type.skill_id,
                work_minutes=work_type.work_minutes,
                priority_id=work_type.priority_id,
            )
            for work_type in work_types
        },
    )


def equipment_quantities(payload: RequestWrite) -> dict[int, int]:
    return {item.equipment_id: item.quantity for item in payload.equipment}


async def apply_work_type_norms(session: AsyncSession, payload: RequestWrite) -> None:
    """Подставляет в заявку нормативы типа работ и проверяет, что длительность и навык заданы.

    Навык определяется типом работ: отдельно его выбирать незачем, иначе два поля об одном
    и том же разъезжаются. Длительность работ на месте берётся из норматива, но её можно
    задать своей: заявка бывает тяжелее норматива.
    """
    references = await load_reference_lookup(session)
    norm = (
        references.work_type_norms.get(payload.work_type_id)
        if payload.work_type_id is not None
        else None
    )
    if norm is not None:
        payload.skill_id = norm.skill_id
        if payload.duration_minutes is None:
            payload.duration_minutes = norm.work_minutes
        # приоритет по умолчанию — из типа работ; заданный в заявке остаётся
        if payload.priority_id is None:
            payload.priority_id = norm.priority_id

    problems = []
    if payload.duration_minutes is None:
        problems.append("укажите длительность работ или выберите тип работ")
    if payload.skill_id is None:
        problems.append("укажите навык или выберите тип работ")
    if payload.priority_id is None:
        problems.append("укажите приоритет или выберите тип работ")
    if problems:
        raise RequestDataError(problems)


async def check_references_exist(session: AsyncSession, payload: RequestWrite) -> None:
    """Проверяет, что приоритет, навык, транспорт, тип работ и оборудование есть в справочниках."""
    references = await load_reference_lookup(session)
    problems = []
    if str(payload.priority_id) not in references.priorities.id_by_key:
        problems.append(f"приоритета №{payload.priority_id} нет в справочнике")
    if payload.skill_id is not None and str(payload.skill_id) not in references.skills.id_by_key:
        problems.append(f"навыка №{payload.skill_id} нет в справочнике")
    if (
        payload.work_type_id is not None
        and str(payload.work_type_id) not in references.work_types.id_by_key
    ):
        problems.append(f"типа работ №{payload.work_type_id} нет в справочнике")
    if (
        payload.transport_id is not None
        and str(payload.transport_id) not in references.transports.id_by_key
    ):
        problems.append(f"транспорта №{payload.transport_id} нет в справочнике")
    missing_equipment = [
        item.equipment_id
        for item in payload.equipment
        if str(item.equipment_id) not in references.equipment.id_by_key
    ]
    if missing_equipment:
        listed = ", ".join(f"№{equipment_id}" for equipment_id in missing_equipment)
        problems.append(f"оборудования {listed} нет в справочнике")
    if problems:
        raise RequestDataError(problems)


async def elsewhere(session: AsyncSession, taken_office_id: int | None, office_id: int) -> str:
    """Где занят номер: в другом офисе запись не видна, и без пояснения ошибка непонятна."""
    if taken_office_id == office_id:
        return " этого офиса"
    office = await session.get(Office, taken_office_id) if taken_office_id else None
    return f" офиса «{office.name}»" if office else " другого офиса"
