"""Настройки запуска, читаемые из переменных окружения."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_PATH = Path("data") / "app.sqlite3"


@dataclass(frozen=True)
class Settings:
    database_path: Path
    enable_api_docs: bool


def load_settings() -> Settings:
    return Settings(
        database_path=Path(os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH)),
        # Документация API включается только явно и только для локальной разработки (SR-02, D-03).
        enable_api_docs=os.environ.get("ENABLE_API_DOCS") == "1",
    )
