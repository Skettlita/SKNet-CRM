import os
from uuid import uuid4

import pytest
from psycopg import connect, sql
from sqlalchemy.engine import make_url


@pytest.fixture
def database(monkeypatch):
    test_url = os.getenv("SKNET_TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("Define SKNET_TEST_DATABASE_URL para un servidor PostgreSQL 17 aislado.")

    admin_url = make_url(test_url).set(drivername="postgresql")
    name = f"sknet_check_{uuid4().hex}"
    database_url = admin_url.set(database=name).render_as_string(hide_password=False)
    with connect(admin_url.render_as_string(hide_password=False), autocommit=True) as admin:
        assert admin.info.server_version // 10000 == 17
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            monkeypatch.setenv("DATABASE_URL", database_url)
            with connect(database_url, autocommit=True) as check:
                yield check
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


