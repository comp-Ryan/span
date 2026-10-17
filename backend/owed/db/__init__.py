from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from owed.config import settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=8, kwargs={"row_factory": dict_row})
    return _pool


@contextmanager
def conn():
    with pool().connection() as c:
        yield c


def apply_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text()
    with psycopg.connect(settings.database_url) as c:
        c.execute(sql)
        c.commit()


def apply_runtime() -> None:
    with conn() as c:
        c.execute((Path(__file__).parent / "runtime.sql").read_text())
