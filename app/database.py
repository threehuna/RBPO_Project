"""SQLite connections and transactional initialization of public demo data."""

from pathlib import Path

from sqlalchemy import Engine, URL, create_engine, event
from sqlalchemy.orm import Session

from app.models import Base, Material


SEED_MATERIALS = (
    {
        "id": 1,
        "title": "Правила учебного сообщества",
        "body": "Синтетический материал для демонстрации каталога и будущих жалоб.",
        "status": "visible",
    },
    {
        "id": 2,
        "title": "Объявление о встрече",
        "body": "Вымышленное объявление. Реальных персональных данных здесь нет.",
        "status": "visible",
    },
    {
        "id": 3,
        "title": "Заметка об учебном проекте",
        "body": "Материал используется только для локальной проверки веб-API.",
        "status": "visible",
    },
)


def create_db_engine(database_path: Path) -> Engine:
    engine = create_engine(
        URL.create("sqlite", database=str(database_path)),
        connect_args={"check_same_thread": False},
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def seed_catalog(session: Session) -> None:
    """Insert missing demo rows without overwriting existing state or committing."""
    for material in SEED_MATERIALS:
        if session.get(Material, material["id"]) is None:
            session.add(Material(**material))
    session.flush()


def initialize_database(engine: Engine) -> None:
    """Create missing tables, then seed the catalog in one all-or-nothing transaction."""
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        seed_catalog(session)
