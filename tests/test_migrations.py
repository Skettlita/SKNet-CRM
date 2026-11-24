from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import errors

from app.main import app


BACKEND = Path(__file__).resolve().parents[1] / "backend"
SCHEMAS = [
    "audit", "billing", "connectivity", "core", "crm",
    "inventory", "monitoring", "platform", "platform_billing",
]


def test_migrations_empty_database_and_health(database):
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    assert database.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004_platform",)
    tables, schemas = database.execute(
        """
        SELECT count(*), count(DISTINCT schemaname)
        FROM pg_tables WHERE schemaname = ANY(%s)
        """,
        (SCHEMAS,),
    ).fetchone()
    assert (tables, schemas) == (79, 9)
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
    assert database.execute("SELECT code FROM platform.features WHERE implemented ORDER BY code").fetchall() == [("ACCESS",), ("SAAS_SUPPORT",)]
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
