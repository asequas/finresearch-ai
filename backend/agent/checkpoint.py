"""LangGraph's Postgres checkpointer, one per process (ADR 0008).

The tables come from Alembic revision b7e3c91a5d24, never from `setup()` at runtime. The checkpoint is the
agent's working memory for one job (thread_id = job id); the domain tables are the record, so a finished
job's thread is deleted.
"""
import threading

from sqlalchemy.engine import make_url

from backend.core.config import settings

_lock = threading.Lock()
_saver = None


def get_checkpointer():
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    global _saver
    with _lock:
        if _saver is None:
            url = make_url(settings.database_url).set(drivername="postgresql").render_as_string(hide_password=False)
            pool = ConnectionPool(
                url, min_size=1, max_size=4, open=True,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            )
            _saver = PostgresSaver(pool)
        return _saver
