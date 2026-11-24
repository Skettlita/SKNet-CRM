import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker


def database_url() -> URL:
    if url := os.getenv("DATABASE_URL"):
        return url_from_environment(url)
    return URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )


def url_from_environment(url: str) -> URL:
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if parsed.drivername in {"postgresql", "postgres"}:
        return parsed.set(drivername="postgresql+psycopg")
    return parsed


def create_database_engine():
    return create_engine(
        database_url(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=3000"},
    )


def create_session_factory(engine):
    return sessionmaker(bind=engine)
