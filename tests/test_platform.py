from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation

from app import cli
from app.db import create_database_engine, create_session_factory
from app.main import app
from test_access import (
    ADMIN_IDENTITY, ORIGIN, PASSWORD, admin_id, change_password, login, make_role,
    migrated, request, signup, user_payload,
)
from test_migrations import BACKEND


TERMS = {
    "name": "Plan configurable", "code": "LOCAL", "description": "Vigencia comercial anual.",
    "price": "25.75", "currency": "USD", "billing_period": "YEARLY", "duration_days": 30,
    "max_users": 2, "max_clients": 4, "max_devices": 6, "min_poll_interval_seconds": 12,
    "retention_days": 20, "features": ["ACCESS", "SAAS_SUPPORT"],
}


def accepted(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def plan(admin, data=TERMS):
    return accepted(request(admin, "POST", "admin/plans", data), 201)


def manual_signup(admin, slug):
    return accepted(request(admin, "POST", "admin/companies", {
        "company": "Empresa " + slug, "name": "Administrador " + slug,
        "username": "isp-" + slug, "email": slug + "@example.com", "phone": "+591 70000000",
        "tax_id": "NIT-" + slug, "password": PASSWORD, "confirm_password": PASSWORD,
    }), 201)


def authentication(client, user=ADMIN_IDENTITY["username"]):
    accepted(login(client, "admin", user))


def settings(client, enabled, version):
    return accepted(request(client, "PUT", "admin/settings", {
        "public_signup_enabled": enabled, "default_plan_version_id": version,
    }))


def test_companies_signup_and_default_plan(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as first, TestClient(app) as second:
        authentication(admin)
        assert accepted(first.get("/api/v1/isp/signup"))["enabled"] is False
        assert signup(first, "bloqueado").status_code == 403
        created = manual_signup(admin, "manual")
        company_id = created["company_id"]
        accepted(login(first, "isp", "isp-manual"))
        assert first.get("/api/v1/admin/companies").status_code == 401
        company = accepted(admin.get(f"/api/v1/admin/companies/{company_id}"))
        assert company["status"] == "ACTIVE"
        assert company["connectivity"] == "UNCONFIGURED"
        assert company["subscription"]["plan_code"] == "TRIAL"
        assert company["subscription"]["ends_at"] is None
        assert company["usage"] == {"clients": 0, "users": 1, "monitored_devices": 0}
        assert accepted(admin.get(f"/api/v1/admin/companies/{company_id}/users"))["items"][0]["id"] == created["user_id"]

        custom = plan(admin)
        version = custom["versions"][0]["version_id"]
        changed = settings(admin, True, version)
        assert changed["id"] == version
        assert accepted(first.get("/api/v1/isp/signup"))["plan"]["version_id"] == version
        registered = accepted(signup(second, "publica"), 201)
        info = accepted(admin.get(f"/api/v1/admin/companies/{registered['company_id']}"))
        assert info["subscription"]["plan_version_id"] == version
        assert info["subscription"]["status"] == "ACTIVE"
        assert info["subscription"]["ends_at"] is not None
        assert info["subscription"]["max_users"] == 2
        settings(admin, False, version)
        assert signup(second, "apagado").status_code == 403
        assert manual_signup(admin, "desactivado")

        edited = accepted(request(admin, "PUT", f"admin/companies/{company_id}", {
            "name": "ISP actualizado", "timezone": "America/La_Paz", "tax_id": "12345",
            "phone": "+591 70000111", "email": "empresa@example.com",
        }))
        assert edited["name"] == "ISP actualizado"
        assert request(admin, "PUT", f"admin/companies/{company_id}", {
            "name": "Zona inválida", "timezone": "no-existe",
        }).status_code == 422
        accepted(request(admin, "PATCH", f"admin/companies/{company_id}/status", {"status": "INACTIVE", "reason": "Prueba DEV"}))
        assert first.get("/api/v1/isp/me").status_code == 401
        assert login(first, "isp", "isp-manual").status_code == 401
        found = accepted(admin.get("/api/v1/admin/companies", params={
            "q": "actualizado", "status": "INACTIVE", "sort": "created", "direction": "desc", "limit": 1,
        }))
        assert len(found["items"]) == 1
        assert found["items"][0]["connectivity"] == "UNCONFIGURED"
        assert found["items"][0]["subscription_status"] == "TRIAL"
        assert accepted(admin.get("/api/v1/admin/companies?limit=1"))["has_more"] is True
        accepted(request(admin, "PATCH", f"admin/companies/{company_id}/status", {"status": "ACTIVE", "reason": "Verificación DEV"}))
        accepted(login(first, "isp", "isp-manual"))
        assert admin.delete(f"/api/v1/admin/companies/{company_id}", headers={"Origin": ORIGIN}).status_code == 405

    assert migrated.execute("SELECT count(*) FROM connectivity.collectors").fetchone() == (0,)
    assert migrated.execute("SELECT count(*) FROM core.users WHERE account_scope='SAAS'").fetchone() == (1,)


def test_plan_versioning_subscription_and_limits(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        company_id = manual_signup(admin, "limites")["company_id"]
        accepted(login(isp, "isp", "isp-limites"))
        accepted(request(isp, "POST", "isp/users", user_payload("existing-account", [])), 201)
        original = accepted(admin.get(f"/api/v1/admin/companies/{company_id}"))["subscription"]
        assert original["plan_code"] == "TRIAL"
        assert request(admin, "POST", "admin/plans", {**TERMS, "features": ["SNMP"]}).status_code == 422
        custom = plan(admin)
        first_version = custom["versions"][0]["version_id"]
        updated_terms = {key: value for key, value in TERMS.items() if key != "code"}
        updated = accepted(request(admin, "PUT", f"admin/plans/{custom['id']}", {
            **updated_terms, "name": "Versión con límite", "price": "31", "max_users": 1,
            "duration_days": None, "features": ["ACCESS"],
        }))
        assert [version["version"] for version in updated["versions"]] == [2, 1]
        assert updated["versions"][1]["version_id"] == first_version
        assert str(updated["versions"][1]["price"]) in {"25.75"}
        assert updated["versions"][0]["billing_period"] == "YEARLY"
        assert updated["versions"][0]["max_devices"] == 6
        assert updated["versions"][0]["retention_days"] == 20
        version = updated["versions"][0]["version_id"]
        change = {"plan_version_id": version, "status": "ACTIVE", "ends_at": None, "reason": "Nuevo contrato"}
        assert request(admin, "POST", f"admin/companies/{company_id}/subscriptions", change).status_code == 409
        with pytest.raises(UniqueViolation):
            migrated.execute("""
                INSERT INTO platform.subscriptions(company_id,plan_version_id) VALUES (%s, %s)
            """, (company_id, version))

        sid = original["id"]
        accepted(request(admin, "PUT", f"admin/subscriptions/{sid}", change))
        detail = accepted(admin.get(f"/api/v1/admin/subscriptions/{sid}"))
        assert detail["max_users"] == 1 and detail["usage"]["users"] == 2
        assert detail["ends_at"] is None
        assert detail["history"][0]["previous_plan"] == "TRIAL"
        assert detail["history"][0]["new_version"] == 2
        assert request(isp, "POST", "isp/users", user_payload("blocked-limit", [])).status_code == 409
        assert isp.get("/api/v1/isp/support/tickets").status_code == 403
        assert isp.get("/api/v1/isp/users").status_code == 200

        settings(admin, False, version)
        assert request(admin, "PATCH", f"admin/plans/{custom['id']}/status", {"active": False}).status_code == 409
        trial = next(item for item in accepted(admin.get("/api/v1/admin/plans/choices")) if item["code"] == "TRIAL")
        settings(admin, False, trial["version_id"])
        accepted(request(admin, "PATCH", f"admin/plans/{custom['id']}/status", {"active": False}))
        assert accepted(admin.get(f"/api/v1/admin/subscriptions/{sid}"))["current"] is True
        future = datetime.now(UTC) + timedelta(days=4)
        invalid = request(admin, "PUT", f"admin/subscriptions/{sid}", {**change, "starts_at": future.isoformat(),
            "ends_at": (future - timedelta(days=1)).isoformat()})
        assert invalid.status_code == 422
        accepted(request(admin, "PUT", f"admin/subscriptions/{sid}", {**change, "status": "CANCELLED"}))
        assert request(admin, "POST", f"admin/companies/{company_id}/subscriptions", change).status_code == 422

        cookie = admin.cookies.get("sknet_saas")
        new = {**change, "plan_version_id": trial["version_id"], "status": "TRIAL"}

        def assign():
            with TestClient(app) as other:
                response = other.post(f"/api/v1/admin/companies/{company_id}/subscriptions",
                    json=new, headers={"Origin": ORIGIN, "Cookie": f"sknet_saas={cookie}"})
                return response.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: assign(), range(2))) == [201, 409]

    assert migrated.execute("SELECT count(*) FROM core.memberships WHERE company_id=%s", (company_id,)).fetchone() == (2,)


def test_support_audit_dashboard_authorization_and_persistence(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp, TestClient(app) as other, TestClient(app) as restricted:
        authentication(admin)
        first = manual_signup(admin, "soporte")
        manual_signup(admin, "otro")
        accepted(login(isp, "isp", "isp-soporte"))
        accepted(login(other, "isp", "isp-otro"))
        path = "isp/support/tickets"
        ticket = accepted(request(isp, "POST", path, {
            "subject": "Consulta operativa", "description": "Solicitud desde el ISP para soporte de SKNet.", "priority": "HIGH",
        }), 201)
        tid = ticket["id"]
        assert other.get(f"/api/v1/{path}/{tid}").status_code == 404
        assert accepted(other.get(f"/api/v1/{path}"))["items"] == []
        assert request(other, "POST", f"{path}/{tid}/replies", {"body": "Cruce"}).status_code == 404
        assert request(isp, "POST", f"{path}/{tid}/replies", {"body": "Privado", "internal": True}).status_code == 403
        assert isp.get("/api/v1/admin/dashboard").status_code == 401
        admin_path = f"admin/support/tickets/{tid}"
        staff = accepted(admin.get("/api/v1/admin/support/assignees"))
        change = {"status": "ASSIGNED", "priority": "HIGH", "assigned_staff_id": staff[0]["id"], "reason": "Atención asignada"}
        assert request(admin, "PUT", admin_path, {**change, "status": "CLOSED"}).status_code == 409
        accepted(request(admin, "PUT", admin_path, change))
        accepted(request(admin, "POST", admin_path + "/replies", {"body": "Respuesta pública"}), 201)
        accepted(request(admin, "POST", admin_path + "/replies", {"body": "Nota privada de prueba", "internal": True}), 201)
        assert [c["body"] for c in accepted(isp.get(f"/api/v1/{path}/{tid}"))["comments"]] == ["Respuesta pública"]
        assert len(accepted(admin.get(f"/api/v1/{admin_path}"))["comments"]) == 2
        selected = accepted(admin.get("/api/v1/admin/support/tickets", params={
            "company_id": first["company_id"], "priority": "HIGH", "status": "ASSIGNED",
        }))
        assert [item["id"] for item in selected["items"]] == [tid]

        known = accepted(admin.get("/api/v1/admin/dashboard"))
        assert known["companies"] == {"registered": 2, "active": 2, "suspended": 0}
        assert known["subscriptions"]["active"] == 2 and known["subscriptions"]["trial"] == 2
        assert known["subscriptions"]["distribution"][0]["companies"] == 2
        assert known["staff_users"] == 1 and known["isp_users"] == 2 and known["open_tickets"] == 1
        assert known["activity"] and known["infrastructure"]["last_measurement"] is None

        events = accepted(admin.get("/api/v1/admin/audit", params={"company_id": first["company_id"]}))["items"]
        assert {"company.register", "subscription.create", "support.create", "support.update", "support.reply"} <= {e["action"] for e in events}
        assert "Nota privada" not in str(events) and PASSWORD not in str(events)
        assert any(e["scope"] == "ISP" and e["actor"] for e in events)
        assert admin.post("/api/v1/admin/audit", headers={"Origin": ORIGIN}).status_code == 405

        role = make_role(admin, "admin", "Informe limitado", ["dashboard.read", "companies.read"])
        limited = accepted(request(admin, "POST", "admin/users", user_payload("dashboard-view", [role])), 201)
        accepted(login(restricted, "admin", "user-dashboard-view", limited["temporary_password"]))
        accepted(change_password(restricted, "admin", limited["temporary_password"]))
        assert set(accepted(restricted.get("/api/v1/admin/dashboard"))) == {"companies"}
        assert restricted.get("/api/v1/admin/audit").status_code == 403
        assert request(restricted, "POST", "admin/plans", TERMS).status_code == 403
        assert request(restricted, "PATCH", f"admin/companies/{first['company_id']}/status",
                       {"status": "INACTIVE", "reason": "Sin permiso"}).status_code == 403
        assert restricted.get(f"/api/v1/admin/companies/{first['company_id']}/users").status_code == 403

        accepted(request(admin, "PUT", admin_path, {**change, "status": "RESOLVED"}))
        accepted(request(admin, "PUT", admin_path, {**change, "status": "CLOSED"}))
        assert accepted(admin.get("/api/v1/admin/dashboard"))["open_tickets"] == 0
        cookie = admin.cookies.get("sknet_saas")

    with TestClient(app) as restarted:
        saved = accepted(restarted.get(f"/api/v1/{admin_path}", headers={"Cookie": f"sknet_saas={cookie}"}))
        assert saved["status"] == "CLOSED" and len(saved["history"]) == 4


def test_platform_upgrade_preserves_existing_data_and_privileges(database, monkeypatch):
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "0003_access")
    answers = iter(ADMIN_IDENTITY.values())
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli, "getpass", lambda _: PASSWORD)
    engine = create_database_engine()
    try:
        with create_session_factory(engine)() as db:
            cli.create_admin(db)
    finally:
        engine.dispose()
    company = database.execute("INSERT INTO core.companies(name) VALUES ('Persistente') RETURNING id").fetchone()[0]
    partial = database.execute("INSERT INTO platform.roles(name) VALUES ('Limitado') RETURNING id").fetchone()[0]
    database.execute("""
        INSERT INTO platform.role_permissions(role_id,permission_id)
        SELECT %s,id FROM platform.permissions WHERE code='dashboard.read'
    """, (partial,))
    command.upgrade(config, "head")
    assert database.execute("SELECT name FROM core.companies WHERE id=%s", (company,)).fetchone() == ("Persistente",)
    assert database.execute("SELECT count(*) FROM platform.role_permissions WHERE role_id=%s", (partial,)).fetchone() == (1,)
    with TestClient(app) as admin:
        authentication(admin)
        assert "plans.write" in accepted(admin.get("/api/v1/admin/me"))["permissions"]
