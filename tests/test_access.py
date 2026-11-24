from secrets import token_urlsafe

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import cli
from app.auth import recovery
from app.auth.security import digest
from app.db import create_database_engine, create_session_factory
from app.main import app
from test_migrations import BACKEND


ORIGIN = "http://testserver"
PASSWORD = token_urlsafe(24)
NEXT_PASSWORD = token_urlsafe(24)
ADMIN_IDENTITY = {"name": "Admin de plataforma", "username": "platform-admin", "email": "platform-admin@example.com"}
TRIAL = {"public_signup_enabled": True, "monthly_price": "0", "trial_days": None, "max_users": None}


def request(client, method, path, data=None):
    return client.request(method, "/api/v1/" + path, json=data, headers={"Origin": ORIGIN})


def login(client, scope, identifier, password=PASSWORD):
    return request(client, "POST", scope + "/login", {"identifier": identifier, "password": password})


def signup(client, label):
    return request(client, "POST", "isp/signup", {
        "company": "Empresa " + label, "tax_id": None, "phone": "+591 70000000",
        "name": "Administrador " + label, "username": "isp-" + label, "email": label + "@example.com",
        "password": PASSWORD, "confirm_password": PASSWORD, "accept_terms": True,
    })


def user_payload(label, roles):
    return {"name": "Usuario " + label, "username": "user-" + label,
            "email": label + "@example.com", "role_ids": roles}


def make_role(client, scope, name, permissions):
    response = request(client, "POST", scope + "/roles", {"name": name, "permissions": permissions})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def change_password(client, scope, current_password):
    return request(client, "POST", scope + "/password", {
        "current_password": current_password, "password": NEXT_PASSWORD, "confirm_password": NEXT_PASSWORD,
    })


@pytest.fixture
def migrated(database, monkeypatch):
    monkeypatch.delenv("SKNET_SMTP_HOST", raising=False)
    monkeypatch.delenv("SKNET_SMTP_FROM", raising=False)
    monkeypatch.setenv("SKNET_ORIGIN", ORIGIN)
    monkeypatch.setenv("SKNET_COOKIE_SECURE", "0")
    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    return database


@pytest.fixture
def admin_id(migrated, monkeypatch):
    answers = iter(ADMIN_IDENTITY.values())

    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(cli, "getpass", lambda _: PASSWORD)
    engine = create_database_engine()
    try:
        with create_session_factory(engine)() as db:
            return str(cli.create_admin(db))
    finally:
        engine.dispose()


def test_bootstrap_login_scope_csrf_rate_limit_and_logout(migrated, admin_id, monkeypatch):
    with TestClient(app) as client:
        for _ in range(8):
            bad = login(client, "admin", "wrong-user", "incorrecta")
            assert bad.status_code == 401
            assert bad.json() == {"detail": "Usuario o contraseña incorrectos."}
        assert login(client, "admin", "wrong-user", "incorrecta").status_code == 429
        assert login(client, "isp", ADMIN_IDENTITY["username"]).status_code == 401
        assert request(client, "POST", "admin/signup", {}).status_code in (404, 405)
        assert client.post("/api/v1/admin/login", json={"identifier": ADMIN_IDENTITY["username"], "password": PASSWORD},
                           headers={"Origin": "http://other.example.com"}).status_code == 403

        response = login(client, "admin", ADMIN_IDENTITY["username"].upper())
        assert response.status_code == 200, response.text
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/api/v1/admin/me").json()["id"] == admin_id
        assert client.get("/api/v1/isp/me").status_code == 401
        old_cookie = client.cookies.get("sknet_saas")
        assert request(client, "POST", "admin/logout").status_code == 204
        assert client.get("/api/v1/admin/me", headers={"Cookie": f"sknet_saas={old_cookie}"}).status_code == 401
        assert login(client, "admin", ADMIN_IDENTITY["email"].upper()).status_code == 200
        invalid = request(client, "POST", "admin/login", {"identifier": "x", "password": "a" * 140})
        assert invalid.status_code == 422
        assert "a" * 140 not in invalid.text

    stored = migrated.execute("SELECT password_hash FROM core.users WHERE id=%s", (admin_id,)).fetchone()[0]
    assert stored.startswith("$argon2id$")
    assert migrated.execute("SELECT count(*) FROM core.sessions WHERE token_hash=%s", (digest(old_cookie),)).fetchone() == (1,)

    answers = iter(ADMIN_IDENTITY.values())
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    engine = create_database_engine()
    try:
        with create_session_factory(engine)() as db, pytest.raises(HTTPException) as error:
            cli.create_admin(db)
        assert error.value.status_code == 409
    finally:
        engine.dispose()


def test_signup_trial_and_persistence(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        assert admin.get("/api/v1/admin/settings").status_code == 401
        assert signup(isp, "uno").status_code == 403
        assert login(admin, "admin", ADMIN_IDENTITY["username"]).status_code == 200
        assert request(admin, "PUT", "admin/settings", TRIAL).status_code == 200
        registered = signup(isp, "uno")
        assert registered.status_code == 201, registered.text
        assert signup(isp, "uno").status_code == 409
        assert login(isp, "isp", "UNO@EXAMPLE.COM").status_code == 200
        assert login(isp, "admin", "isp-uno").status_code == 401
        company_id = registered.json()["company_id"]
        account = isp.get("/api/v1/isp/me").json()
        assert account["company_id"] == company_id
        assert account["plan"]["code"] == "TRIAL"
        token = isp.cookies.get("sknet_isp")
        updated = request(admin, "PUT", "admin/settings", {**TRIAL, "trial_days": 7, "max_users": 1})
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == 2
        assert signup(isp, "dos").status_code == 201
        assert request(admin, "PUT", "admin/settings", {**TRIAL, "public_signup_enabled": False}).status_code == 200
        assert signup(isp, "tres").status_code == 403

    with TestClient(app) as restarted:
        result = restarted.get("/api/v1/isp/me", headers={"Cookie": f"sknet_isp={token}"})
        assert result.status_code == 200
        assert result.json()["company_id"] == company_id
        assert result.json()["plan"]["version"] == 1
        assert login(restarted, "isp", "isp-dos").status_code == 200
        blocked = request(restarted, "POST", "isp/users", user_payload("limite", []))
        assert blocked.status_code == 409

    assert migrated.execute("SELECT count(*) FROM core.companies").fetchone() == (2,)
    assert migrated.execute("SELECT count(*) FROM connectivity.collectors").fetchone() == (0,)
    assert migrated.execute("SELECT count(*) FROM crm.clients").fetchone() == (0,)
    assert migrated.execute("""
        SELECT v.monthly_price, v.trial_days, s.ends_at FROM platform.subscriptions s
        JOIN platform.plan_versions v ON v.id = s.plan_version_id WHERE s.company_id=%s
    """, (company_id,)).fetchone() == (0, None, None)
    assert migrated.execute("SELECT count(*) FROM audit.events WHERE action='terms.accept'").fetchone() == (2,)


def test_roles_employees_plan_and_company_boundaries(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as first, TestClient(app) as second, TestClient(app) as employee:
        assert login(admin, "admin", ADMIN_IDENTITY["username"]).status_code == 200
        assert request(admin, "PUT", "admin/settings", TRIAL).status_code == 200
        company = signup(first, "uno").json()["company_id"]
        assert signup(second, "dos").status_code == 201
        assert login(first, "isp", "isp-uno").status_code == 200
        assert login(second, "isp", "isp-dos").status_code == 200
        first_role = make_role(first, "isp", "Lectura", ["dashboard.read", "users.read"])
        second_role = make_role(first, "isp", "Editor de usuarios", ["users.write", "roles.read", "roles.write"])
        outsider = make_role(second, "isp", "Externo", ["dashboard.read"])
        assert request(first, "POST", "isp/users", user_payload("cross-role", [outsider])).status_code == 404
        created = request(first, "POST", "isp/users", user_payload("lectura", [first_role]))
        assert created.status_code == 201, created.text
        employee_id = created.json()["id"]
        temporary = created.json()["temporary_password"]
        assert login(employee, "isp", "user-lectura", temporary).status_code == 200
        assert employee.get("/api/v1/isp/me").json()["permissions"] == []
        assert employee.get("/api/v1/isp/users").status_code == 403
        with TestClient(app) as duplicate:
            assert login(duplicate, "isp", "user-lectura", temporary).status_code == 401
        assert change_password(employee, "isp", temporary).status_code == 200
        assert employee.get("/api/v1/isp/me").json()["permissions"] == ["dashboard.read", "users.read"]
        assert employee.get("/api/v1/isp/roles").status_code == 403
        result = employee.get("/api/v1/isp/users").json()
        assert all(not user["editable"] and not user["resettable"] and "role_ids" not in user for user in result["items"])
        assert all(user["username"] != "isp-dos" for user in result["items"])
        assert request(employee, "POST", "isp/roles", {"name": "Escalar", "permissions": ["users.write"]}).status_code == 403

        edited = request(first, "PUT", f"isp/users/{employee_id}", {
            **user_payload("lectura", [first_role, second_role]), "active": True,
        })
        assert edited.status_code == 200, edited.text
        assert "roles.write" in employee.get("/api/v1/isp/me").json()["permissions"]
        assert request(employee, "POST", "isp/roles", {"name": "Escalar", "permissions": ["users.reset"]}).status_code == 403
        admin_role = next(item["id"] for item in first.get("/api/v1/isp/roles").json()["items"] if item["name"] == "Administración")
        assert request(employee, "POST", "isp/users", user_payload("escalado", [admin_role])).status_code == 403
        assert request(second, "PUT", f"isp/users/{employee_id}", {
            **user_payload("lectura", []), "active": False,
        }).status_code == 404
        assert request(second, "PUT", f"isp/roles/{first_role}", {"name": "Ajeno", "permissions": []}).status_code == 404
        assert request(first, "PUT", f"isp/roles/{admin_role}", {"name": "Administración", "permissions": []}).status_code == 409

        migrated.execute("UPDATE platform.subscriptions SET status='SUSPENDED' WHERE company_id=%s", (company,))
        assert employee.get("/api/v1/isp/me").json()["permissions"] == []
        assert employee.get("/api/v1/isp/users").status_code == 403
        migrated.execute("UPDATE platform.subscriptions SET status='TRIAL' WHERE company_id=%s", (company,))
        reset = request(first, "POST", f"isp/users/{employee_id}/reset")
        assert reset.status_code == 200
        assert employee.get("/api/v1/isp/me").status_code == 401
        assert request(first, "PUT", f"isp/users/{employee_id}", {
            **user_payload("lectura", []), "active": False,
        }).status_code == 200
        assert login(employee, "isp", "user-lectura", reset.json()["temporary_password"]).status_code == 401


def test_recovery_and_saas_last_administrator(migrated, admin_id, monkeypatch):
    captured = []
    monkeypatch.setattr(recovery, "send_access_link", lambda *args: captured.append(args))
    monkeypatch.setenv("SKNET_SMTP_HOST", "mail.example.com")
    monkeypatch.setenv("SKNET_SMTP_FROM", "no-reply@example.com")
    with TestClient(app) as admin, TestClient(app) as isp:
        assert login(admin, "admin", ADMIN_IDENTITY["username"]).status_code == 200
        role = admin.get("/api/v1/admin/roles").json()["items"][0]
        assert request(admin, "PUT", f"admin/roles/{role['id']}", {"name": role["name"], "permissions": []}).status_code == 409
        secondary = request(admin, "POST", "admin/users", user_payload("saas-dos", [role["id"]]))
        assert secondary.status_code == 201, secondary.text
        with TestClient(app) as deputy:
            temporary = secondary.json()["temporary_password"]
            assert login(deputy, "admin", "user-saas-dos", temporary).status_code == 200
            assert request(deputy, "PUT", f"admin/users/{admin_id}", {
                **ADMIN_IDENTITY, "active": False,
            }).status_code == 403
            assert change_password(deputy, "admin", temporary).status_code == 200
            assert request(deputy, "PUT", f"admin/users/{admin_id}", {
                **ADMIN_IDENTITY, "active": True, "role_ids": [role["id"]],
            }).status_code == 200
        assert request(admin, "PUT", "admin/settings", TRIAL).status_code == 200
        assert signup(isp, "uno").status_code == 201
        assert captured[-1][3] == "verify"
        assert request(isp, "POST", "isp/verify", {"token": captured[-1][2]}).status_code == 200
        assert login(isp, "isp", "isp-uno").status_code == 200
        known = request(isp, "POST", "isp/recover", {"email": "uno@example.com"})
        unknown = request(isp, "POST", "isp/recover", {"email": "missing@example.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert captured[-1][3] == "reset"
        reset = {"token": captured[-1][2], "password": NEXT_PASSWORD, "confirm_password": NEXT_PASSWORD}
        assert request(isp, "POST", "isp/recover/confirm", reset).status_code == 200
        assert request(isp, "POST", "isp/recover/confirm", reset).status_code == 400
        assert isp.get("/api/v1/isp/me").status_code == 401
        assert login(isp, "isp", "isp-uno", NEXT_PASSWORD).status_code == 200

        reset_data = {"identifier": "isp-uno", "reason": "Identidad comprobada en prueba", "identity_verified": False}
        assert request(admin, "POST", "admin/support/reset", reset_data).status_code == 422
        reset_data["identity_verified"] = True
        support = request(admin, "POST", "admin/support/reset", reset_data)
        assert support.status_code == 200
        assert isp.get("/api/v1/isp/me").status_code == 401
        assert login(isp, "isp", "isp-uno", support.json()["temporary_password"]).status_code == 200
        assert change_password(isp, "isp", support.json()["temporary_password"]).status_code == 200

    monkeypatch.setattr("builtins.input", lambda _: ADMIN_IDENTITY["username"])
    engine = create_database_engine()
    try:
        with create_session_factory(engine)() as db:
            temporary = cli.reset_admin(db)
    finally:
        engine.dispose()
    with TestClient(app) as client:
        assert login(client, "admin", ADMIN_IDENTITY["email"], temporary).status_code == 200
        assert client.get("/api/v1/admin/settings").status_code == 403
        assert change_password(client, "admin", temporary).status_code == 200
