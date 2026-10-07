"""Точка входа FastAPI: `python -m uvicorn app.main:app`."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, load_settings
from app.database import create_db_engine, create_session_factory
from app.models import Base, Material
from app.seed import seed_catalog

logger = logging.getLogger("app")

SQLITE_MAX_INTEGER = 2**63 - 1


class MaterialOut(BaseModel):
    """Публичные поля материала; статус и прочие внутренние поля не выдаются (D-03)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str


class PageParams(BaseModel):
    """Параметры выдачи списка. Неизвестные параметры запрещены (D-03)."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=SQLITE_MAX_INTEGER)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = create_db_engine(settings.database_path)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            settings.database_path.parent.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(engine)
            seed_catalog(session_factory)
        except Exception:
            # Сервер продолжает запуск: /health покажет недоступность, а частичного каталога нет.
            logger.error("database initialization failed")
        yield
        engine.dispose()

    docs = settings.enable_api_docs
    app = FastAPI(
        title="Разбор жалоб на контент",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    def get_session():
        with session_factory() as session:
            yield session

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, _exc: RequestValidationError):
        # Входное значение и структура ошибки не отражаются в ответе (D-03, T-09).
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(_request: Request, _exc: SQLAlchemyError):
        logger.error("database error")
        return JSONResponse(status_code=503, content={"detail": "Service unavailable"})

    @app.exception_handler(Exception)
    async def _unexpected_error(_request: Request, _exc: Exception):
        logger.error("unexpected error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health")
    def health(session: Session = Depends(get_session)):
        try:
            session.execute(select(Material.id).limit(1)).all()
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "database": "error"}
            )
        return {"status": "ok", "database": "ok"}

    @app.get("/materials", response_model=list[MaterialOut])
    def list_materials(
        page: PageParams = Query(), session: Session = Depends(get_session)
    ) -> list[Material]:
        # Скрытые материалы отфильтровываются до пагинации; значения передаются связанными параметрами.
        query = (
            select(Material)
            .where(Material.status == "visible")
            .order_by(Material.id)
            .limit(page.limit)
            .offset(page.offset)
        )
        return list(session.scalars(query))

    return app


app = create_app()
