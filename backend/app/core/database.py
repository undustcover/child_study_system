from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine = create_engine(settings.resolved_database_url, echo=False)


def ensure_data_dir() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    ensure_data_dir()
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    from app.services.students import get_or_create_default_student

    with Session(engine) as session:
        get_or_create_default_student(session)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
