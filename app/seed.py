"""Начальное заполнение учебного каталога (SR-08, T-08).

Каталог задан константой в версионируемом коде; внешний импорт не поддерживается.
Заполнение выполняется одной транзакцией и добавляет только отсутствующие записи:
существующие материалы, в том числе скрытые, не перезаписываются.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import MATERIAL_STATUSES, Material

CATALOG: tuple[dict, ...] = (
    {
        "id": 1,
        "title": "Введение в HTTP",
        "body": "Синтетический учебный материал о методах и кодах ответа HTTP.",
        "status": "visible",
    },
    {
        "id": 2,
        "title": "Основы SQL",
        "body": "Синтетический учебный материал о запросах SELECT, INSERT и UPDATE.",
        "status": "visible",
    },
    {
        "id": 3,
        "title": "Транзакции в базах данных",
        "body": "Синтетический учебный материал о свойствах ACID и блокировках.",
        "status": "visible",
    },
)


class SeedError(Exception):
    """Начальный каталог не прошёл проверку."""


def seed_catalog(session_factory: sessionmaker, catalog: tuple[dict, ...] = CATALOG) -> int:
    """Добавляет отсутствующие материалы каталога. Возвращает число добавленных записей."""
    with session_factory() as session, session.begin():
        return _insert_missing(session, catalog)


def _insert_missing(session: Session, catalog: tuple[dict, ...]) -> int:
    existing_ids = set(session.scalars(select(Material.id)))
    added = 0
    for item in catalog:
        if item["status"] not in MATERIAL_STATUSES:
            # Исключение внутри session.begin() откатывает все вставки этого запуска.
            raise SeedError("invalid material status in built-in catalog")
        if item["id"] in existing_ids:
            continue
        session.add(Material(**item))
        session.flush()
        added += 1
    return added
