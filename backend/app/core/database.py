from collections.abc import Generator
from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine = create_engine(settings.resolved_database_url, echo=False)


def ensure_data_dir() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    ensure_data_dir()
    import app.models  # noqa: F401

    _reset_default_sqlite_db_when_schema_is_stale()
    SQLModel.metadata.create_all(engine)
    from app.services.students import get_or_create_default_student

    with Session(engine) as session:
        get_or_create_default_student(session)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _reset_default_sqlite_db_when_schema_is_stale() -> None:
    if not _uses_default_sqlite_db():
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if not table_names:
        return

    expected_columns = {
        table.name: {column.name for column in table.columns}
        for table in SQLModel.metadata.sorted_tables
    }
    schema_is_stale = any(
        table_name in table_names
        and not expected_columns_for_table.issubset(
            {column["name"] for column in inspector.get_columns(table_name)}
        )
        for table_name, expected_columns_for_table in expected_columns.items()
    )
    if not schema_is_stale:
        return

    engine.dispose()
    (settings.data_dir / "app.db").unlink(missing_ok=True)


def _uses_default_sqlite_db() -> bool:
    if settings.database_url is not None:
        return False
    return Path(settings.resolved_database_url.removeprefix("sqlite:///")) == settings.data_dir / "app.db"
