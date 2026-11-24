import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import connect, errors, sql
from sqlalchemy.engine import make_url

from app.main import app


BACKEND = Path(__file__).resolve().parents[1] / "backend"
SCHEMAS = [
    "audit", "billing", "connectivity", "core", "crm",
    "inventory", "monitoring", "platform", "platform_billing",
]


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


def test_migrations_empty_database_and_health(database):
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    assert database.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002_catalog",)
    tables, schemas = database.execute(
        """
        SELECT count(*), count(DISTINCT schemaname)
        FROM pg_tables WHERE schemaname = ANY(%s)
        """,
        (SCHEMAS,),
    ).fetchone()
    assert (tables, schemas) == (78, 9)
    assert database.execute(
        "SELECT count(*) FROM pg_views WHERE schemaname = ANY(%s)",
        (SCHEMAS,),
    ).fetchone() == (5,)
    assert database.execute(
        """
        SELECT code, monthly_price, currency, trial_days, public_signup_enabled
        FROM platform.settings s
        JOIN platform.plan_versions v ON v.id = s.default_plan_version_id
        JOIN platform.plans p ON p.id = v.plan_id
        """
    ).fetchone() == ("TRIAL", 0, "BOB", None, False)
    assert database.execute("SELECT count(*) FROM platform.features WHERE implemented").fetchone() == (0,)
    assert database.execute("SELECT count(*) FROM core.companies").fetchone() == (0,)
    assert database.execute("SELECT count(*) FROM core.users").fetchone() == (0,)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}


def test_migration_preserves_data_and_rejects_cross_company_link(database):
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "0001_schema")
    first, second = [
        database.execute("INSERT INTO core.companies(name) VALUES (%s) RETURNING id", (name,)).fetchone()[0]
        for name in ("Primera", "Segunda")
    ]
    customer_id = database.execute(
        "INSERT INTO crm.clients(company_id, client_code, name) VALUES (%s, '1', 'Cliente') RETURNING id",
        (first,),
    ).fetchone()[0]

    command.upgrade(config, "head")
    assert database.execute("SELECT name FROM core.companies ORDER BY name").fetchall() == [
        ("Primera",), ("Segunda",),
    ]
    assert database.execute("SELECT company_id FROM crm.clients WHERE id=%s", (customer_id,)).fetchone() == (first,)

    with pytest.raises(errors.ForeignKeyViolation):
        database.execute(
            "INSERT INTO crm.client_contacts(company_id, client_id, name) VALUES (%s, %s, 'Contacto')",
            (second, customer_id),
        )
