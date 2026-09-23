"""Ответы на групповые действия: оператор отмечает строки галочками и меняет или удаляет их разом.

Правка идёт либо целиком, либо никак: расходиться половиной изменений нельзя. Удаление
наоборот — удаляем всё, что можно, а по остальному честно перечисляем причины: одна заявка
в плане не должна отменять удаление остальных двадцати.
"""

from pydantic import BaseModel, Field


class BulkIds(BaseModel):
    """Номера записей, с которыми работаем группой."""

    ids: list[int] = Field(min_length=1)


class BulkUpdateReport(BaseModel):
    updated: int


class BulkDeleteProblem(BaseModel):
    """Запись, которую удалить не вышло, и почему."""

    id: int
    reason: str


class BulkDeleteReport(BaseModel):
    deleted: int
    problems: list[BulkDeleteProblem] = []
