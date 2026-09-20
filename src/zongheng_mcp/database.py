from collections.abc import Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.sql.elements import TextClause

from .config import DbSettings


def build_database_url(settings: DbSettings) -> URL:
    return URL.create(
        drivername="mysql+pymysql",
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.name,
        query={"charset": "utf8mb4"},
    )


class Database:
    def __init__(self, settings: DbSettings, *, engine: Engine | None = None):
        self.engine = engine or create_engine(
            build_database_url(settings),
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            connect_args={
                "connect_timeout": settings.connect_timeout,
                "read_timeout": settings.read_timeout,
                "write_timeout": settings.read_timeout,
                "charset": "utf8mb4",
            },
        )

    def rows(self, statement: TextClause, params: Mapping) -> list[dict]:
        with self.engine.connect() as connection:
            result = connection.execute(statement, dict(params))
            return [dict(row) for row in result.mappings().all()]

    def scalar(self, statement: TextClause, params: Mapping):
        with self.engine.connect() as connection:
            return connection.execute(statement, dict(params)).scalar()

    def dispose(self) -> None:
        self.engine.dispose()
