"""Проверки минимальной запускаемой основы.

Проверяют только реализованный объём: инициализацию, публичный каталог,
ограничения запросов, безопасные ошибки и ограничения схемы. Будущие проверки
D-01/D-02 здесь не выполняются.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.database import create_db_engine, create_session_factory
from app.main import create_app
from app.models import Base, Complaint, Decision, Material, User
from app.seed import CATALOG, SeedError, seed_catalog


def make_client(db_path: Path, docs: bool = False) -> TestClient:
    return TestClient(create_app(Settings(database_path=db_path, enable_api_docs=docs)))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "app.sqlite3"


def test_fresh_database_has_full_visible_catalog(db_path):
    with make_client(db_path) as client:
        health = client.get("/health")
        materials = client.get("/materials")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "ok"}
    assert materials.status_code == 200
    body = materials.json()
    assert [m["id"] for m in body] == [item["id"] for item in CATALOG]
    assert all(set(m) == {"id", "title", "body"} for m in body)


def test_restart_keeps_hidden_material_and_does_not_duplicate(db_path):
    with make_client(db_path):
        pass
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE materials SET status = 'hidden' WHERE id = 2")

    with make_client(db_path) as client:
        ids = [m["id"] for m in client.get("/materials").json()]

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT id, status FROM materials ORDER BY id").fetchall()
    assert ids == [1, 3]
    assert rows == [(1, "visible"), (2, "hidden"), (3, "visible")]


def test_hidden_materials_are_filtered_before_pagination(db_path):
    with make_client(db_path):
        pass
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE materials SET status = 'hidden' WHERE id = 1")

    with make_client(db_path) as client:
        page = client.get("/materials", params={"limit": 1, "offset": 0}).json()
    assert [m["id"] for m in page] == [2]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 2**63},
        {"limit": "abc"},
        {"sort": "title"},
        {"filter": "1=1"},
    ],
)
def test_invalid_list_parameters_are_rejected_without_echo(db_path, params):
    with make_client(db_path) as client:
        response = client.get("/materials", params=params)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_sql_metacharacters_in_parameter_do_not_change_database(db_path):
    with make_client(db_path) as client:
        response = client.get("/materials", params={"limit": "1; DROP TABLE materials; --"})
        assert response.status_code == 422
        assert len(client.get("/materials").json()) == len(CATALOG)


def test_api_docs_disabled_by_default_and_enabled_explicitly(db_path, tmp_path):
    with make_client(db_path) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
    with make_client(tmp_path / "docs.sqlite3", docs=True) as client:
        assert client.get("/openapi.json").status_code == 200


def test_no_complaint_or_decision_routes_yet(db_path):
    with make_client(db_path) as client:
        assert client.get("/complaints").status_code == 404
        assert client.post("/complaints", json={"material_id": 1, "reason": "x"}).status_code == 404


def test_failed_seed_rolls_back_all_inserts(db_path):
    db_path.parent.mkdir(parents=True)
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    broken = CATALOG + ({"id": 99, "title": "x", "body": "x", "status": "deleted"},)

    with pytest.raises(SeedError):
        seed_catalog(create_session_factory(engine), broken)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM materials").fetchone() == (0,)
    engine.dispose()


def test_schema_constraints_and_foreign_keys(db_path):
    db_path.parent.mkdir(parents=True)
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    seed_catalog(session_factory)

    with session_factory() as session, session.begin():
        session.add_all(
            [
                User(id=1, login="user", password_hash="-", role="user"),
                User(id=2, login="moderator", password_hash="-", role="moderator"),
            ]
        )
        session.flush()
        session.add(Complaint(id=1, author_id=1, material_id=1, reason="спорный материал"))
        session.flush()
        session.add(Decision(complaint_id=1, moderator_id=2, result="accepted", reason="нарушение"))

    invalid = [
        Decision(complaint_id=1, moderator_id=2, result="rejected", reason="повтор"),
        Complaint(author_id=1, material_id=404, reason="нет материала"),
        Material(id=50, title="x", body="x", status="deleted"),
        User(login="admin", password_hash="-", role="admin"),
    ]
    for row in invalid:
        with session_factory() as session:
            session.add(row)
            with pytest.raises(IntegrityError):
                session.commit()

    with session_factory() as session:
        assert session.query(Decision).count() == 1
    engine.dispose()


def test_health_returns_safe_503_when_schema_is_broken(db_path):
    with make_client(db_path) as client:
        # Таблица удаляется после старта: при запуске create_all создал бы её заново.
        conn = sqlite3.connect(db_path)
        conn.execute("DROP TABLE materials")
        conn.commit()
        conn.close()
        health = client.get("/health")
        materials = client.get("/materials")

    assert health.status_code == 503
    assert materials.status_code == 503
    for response in (health, materials):
        assert "materials" not in response.text
        assert "sqlite" not in response.text.lower()
