"""Checks of the EK1 foundation, not of the planned authentication/moderation."""

import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import database
from app.main import create_app
from app.models import Material


def test_fresh_database_and_health(tmp_path):
    path = tmp_path / "nested" / "app.sqlite3"
    with TestClient(create_app(database_path=path)) as client:
        assert client.get("/health").json() == {"status": "ok", "database": "ok"}
        response = client.get("/materials")
        assert response.status_code == 200
        assert len(response.json()) == 3
        assert all(set(row) == {"id", "title", "body"} for row in response.json())
    assert path.is_file()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] == 0


def test_restart_preserves_hidden_material_and_filters_before_pagination(tmp_path):
    path = tmp_path / "app.sqlite3"
    app = create_app(database_path=path)
    with TestClient(app) as client:
        initial = client.get("/materials").json()
        hidden_id = initial[0]["id"]
        with Session(app.state.engine) as session, session.begin():
            session.execute(
                update(Material).where(Material.id == hidden_id).values(status="hidden", body="changed locally")
            )
        page = client.get("/materials?limit=1&offset=0").json()
        assert page == [initial[1]]
    # Opening a new application repeats initialization against the existing file.
    restarted = create_app(database_path=path)
    with TestClient(restarted) as client:
        assert client.get("/materials").json() == initial[1:]
        with Session(restarted.state.engine) as session:
            stored = session.get(Material, hidden_id)
            assert stored.status == "hidden"
            assert stored.body == "changed locally"
            assert len(session.scalars(select(Material)).all()) == 3


@pytest.mark.parametrize(
    "query",
    [
        "limit=0", "limit=101", "offset=-1", "offset=9223372036854775808",
        "limit=secret-marker", "sort=secret-marker",
    ],
)
def test_invalid_query_is_rejected_without_reflection(tmp_path, query):
    with TestClient(create_app(database_path=tmp_path / "app.sqlite3")) as client:
        response = client.get("/materials?" + query)
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
        assert "secret-marker" not in response.text
        assert len(client.get("/materials").json()) == 3


def test_default_and_maximum_page_size(tmp_path):
    app = create_app(database_path=tmp_path / "app.sqlite3")
    with TestClient(app) as client:
        with Session(app.state.engine) as session, session.begin():
            session.add_all(
                Material(id=index, title=f"Material {index}", body="Synthetic", status="visible")
                for index in range(100, 220)
            )
        assert len(client.get("/materials").json()) == 20
        assert len(client.get("/materials?limit=100").json()) == 100
        assert client.get("/materials?offset=1000").json() == []


def test_documentation_requires_explicit_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    with TestClient(create_app(database_path=tmp_path / "app.sqlite3")) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.post("/complaints", json={"role": "moderator"}).status_code == 404
    with TestClient(create_app(database_path=tmp_path / "app.sqlite3", enable_docs=True)) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_failed_seed_rolls_back_all_new_rows(tmp_path, monkeypatch):
    engine = database.create_db_engine(tmp_path / "app.sqlite3")
    original = database.SEED_MATERIALS
    broken = [dict(row) for row in original]
    broken[-1]["status"] = "invalid"
    monkeypatch.setattr(database, "SEED_MATERIALS", tuple(broken))
    try:
        with pytest.raises(IntegrityError):
            database.initialize_database(engine)
        with Session(engine) as session:
            assert session.scalars(select(Material)).all() == []
        monkeypatch.setattr(database, "SEED_MATERIALS", original)
        database.initialize_database(engine)
        with Session(engine) as session:
            assert len(session.scalars(select(Material)).all()) == 3
    finally:
        engine.dispose()


def test_foreign_keys_enabled_on_every_connection(tmp_path):
    engine = database.create_db_engine(tmp_path / "app.sqlite3")
    try:
        database.initialize_database(engine)
        with engine.connect() as first, engine.connect() as second:
            assert first.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert second.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        engine.dispose()


def test_database_error_does_not_disclose_internal_details(tmp_path):
    app = create_app(database_path=tmp_path / "private-marker.sqlite3")
    with TestClient(app) as client:
        with app.state.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE materials")
        response = client.get("/materials")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert "private-marker" not in response.text
        assert "SELECT" not in response.text
        assert client.get("/health").status_code == 503
