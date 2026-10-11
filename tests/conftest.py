import os
import uuid
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values
from psycopg.conninfo import make_conninfo

from bot.storage import Store


@pytest.fixture
def store():
    dsn = os.getenv("TEST_DATABASE_URL") or dotenv_values(Path(".local/db.env")).get("DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    dsn = make_conninfo(dsn, connect_timeout=5)
    schema = "test_librarybot_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    result = Store(make_conninfo(dsn, options="-c search_path=" + schema))
    result.migrate()
    yield result
    result.close()
    assert schema.startswith("test_librarybot_")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(psycopg.sql.Identifier(schema))
        )
