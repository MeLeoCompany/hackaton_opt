"""Общие ошибки сервисов. Обработчики в src/main.py превращают их в HTTP-ответы."""


class NotFoundError(Exception):
    """Запрошенной записи нет -> 404."""


class InUseError(Exception):
    """Запись нельзя удалить: на неё ссылаются другие данные -> 409."""


class ExternalServiceError(Exception):
    """Внешний сервис (маршрутизатор Valhalla, решатель cuOpt) недоступен или ответил ошибкой -> 503."""


class DataError(Exception):
    """Данные не прошли проверку -> 422. messages — понятные диспетчеру причины."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages
