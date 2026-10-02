"""Read-only EK1 foundation. Authentication and complaint workflows are future work."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import create_db_engine, initialize_database
from app.models import Material
from app.schemas import CatalogQuery, PublicMaterial


def create_app(
    database_path: Path | None = None, enable_docs: bool | None = None
) -> FastAPI:
    path = Path(database_path or os.environ.get("DATABASE_PATH", "data/app.sqlite3"))
    docs_enabled = enable_docs if enable_docs is not None else os.environ.get("ENABLE_API_DOCS") == "1"

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_db_engine(path)
        application.state.engine = engine
        try:
            initialize_database(engine)
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="Разбор жалоб на контент",
        version="0.1.0",
        debug=False,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @application.exception_handler(SQLAlchemyError)
    async def database_unavailable(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @application.get("/health")
    def health(request: Request) -> dict[str, str]:
        with Session(request.app.state.engine) as session:
            session.execute(select(Material.id).limit(1)).first()
        return {"status": "ok", "database": "ok"}

    @application.get("/materials", response_model=list[PublicMaterial])
    def materials(request: Request, query: Annotated[CatalogQuery, Query()]) -> list[PublicMaterial]:
        statement = (
            select(Material)
            .where(Material.status == "visible")
            .order_by(Material.id)
            .offset(query.offset)
            .limit(query.limit)
        )
        with Session(request.app.state.engine) as session:
            return [PublicMaterial.model_validate(row) for row in session.scalars(statement)]

    return application


app = create_app()
