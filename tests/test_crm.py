from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import app
from test_access import PASSWORD, admin_id, change_password, login, make_role, migrated, request, user_payload
from test_migrations import BACKEND
from test_platform import TERMS, accepted, authentication, manual_signup, plan, settings


CRM = "isp/crm/"
SWITCH = {"active": False, "reason": "Prueba de estado administrativo"}


def make(client, kind, data):
    return accepted(request(client, "POST", CRM + kind, data), 201)


def get(client, path, params=None):
    return accepted(client.get("/api/v1/" + CRM + path, params=params))


def client_fields(name="Cliente Uno"):
    return {"client_type": "PERSON", "name": name, "document_type": "CI",
            "document_number": "1234", "phone": "+591 70001234", "email": "cliente@example.com"}


def make_client(client, name="Cliente Uno"):
    return make(client, "clients", client_fields(name))


def make_plan(client):
    return make(client, "internet-plans", {
        "name": "Fibra 100", "description": "Fibra residencial", "download_mbps": 100, "upload_mbps": 30,
        "monthly_price": "160.50", "currency": "BOB", "observations": "Instalación programada",
    })


def make_site(client, name, customer=None):
    return make(client, "sites", {"name": name, "site_type": "CLIENT_SITE" if customer else "NODE",
            "client_id": customer["id"] if customer else None, "address": "Calle de prueba", "city": "La Paz",
            "latitude": "-16.5", "longitude": "-68.15", "description": "Ubicación de prueba"})


def device_data(site, ip="192.168.10.2", name="Equipo de prueba", service=None):
    return {"name": name, "site_id": site["id"], "device_role": "ENDPOINT", "device_type": "ONT",
            "brand": "Fabricante abierto", "model": "AX-10", "ip_address": ip, "description": "Equipo de validación",
            "service_id": service["id"] if service else None}


def test_clients_contacts_addresses_notes_and_state(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        manual_signup(admin, "clientes")
        accepted(login(isp, "isp", "isp-clientes"))
        customer = make_client(isp)
        cid = customer["id"]
        updated = accepted(request(isp, "PUT", CRM + f"clients/{cid}", {
            **client_fields("Empresa Uno"), "client_type": "COMPANY",
            "document_type": "NIT", "observations": "Nota previa",
        }))
        assert updated["name"] == "Empresa Uno" and updated["client_type"] == "COMPANY"
        assert updated["client_code"] == customer["client_code"] == "CLI-000001"
        assert request(isp, "POST", CRM + "clients", {**client_fields(), "client_code": "CLI-000001"}).status_code == 422

        first = make(isp, f"clients/{cid}/contacts", {"name": "Contacto Uno", "is_primary": True})
        second = make(isp, f"clients/{cid}/contacts", {"name": "Contacto Dos", "is_primary": True})
        contacts = get(isp, f"clients/{cid}/contacts")["items"]
        assert [entry["id"] for entry in contacts if entry["is_primary"]] == [second["id"]]
        accepted(request(isp, "PUT", CRM + f"clients/{cid}/contacts/{first['id']}", {
            "name": "Contacto editado", "phone": "+591 70001345", "is_primary": False,
        }))
        address = make(isp, f"clients/{cid}/addresses", {"address": "Calle Uno", "city": "La Paz", "address_type": "BILLING"})
        assert accepted(request(isp, "PUT", CRM + f"clients/{cid}/addresses/{address['id']}", {
            "address": "Calle Dos", "address_type": "LEGAL",
        }))["address"] == "Calle Dos"
        make(isp, f"clients/{cid}/notes", {"body": "Nota de atención"})
        assert get(isp, f"clients/{cid}/notes")["items"][0]["body"] == "Nota de atención"
        accepted(request(isp, "PATCH", CRM + f"clients/{cid}/status", SWITCH))
        found = get(isp, "clients", {"q": "empresa", "status": "INACTIVE", "category": "COMPANY", "sort": "created", "direction": "desc", "limit": 1})
        assert [item["id"] for item in found["items"]] == [cid]
        assert get(isp, f"clients/{cid}")["status"] == "INACTIVE"
        assert get(isp, f"clients/{cid}/contacts")["items"]
        assert isp.delete("/api/v1/" + CRM + f"clients/{cid}").status_code == 405
        accepted(request(isp, "PATCH", CRM + f"clients/{cid}/status", {**SWITCH, "active": True}))
        changes = get(isp, f"clients/{cid}/activity")["items"]
        assert {"crm.client.update", "crm.address.update", "crm.contact.create", "crm.client_note.create"} <= {item["action"] for item in changes}


def test_services_sites_and_device_configuration(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        company = manual_signup(admin, "red")
        accepted(login(isp, "isp", "isp-red"))
        customer = make_client(isp)
        plan_record = make_plan(isp)
        own = make_site(isp, "Nodo propio")
        first_site = make_site(isp, "Instalación uno", customer)
        second_site = make_site(isp, "Instalación dos", customer)
        router = make(isp, "devices", {
            **device_data(own, "192.168.10.1", "Router central"), "device_role": "NODE", "device_type": "Router",
            "capabilities": ["PPPOE_SERVER", "DHCP_SERVER", "ACCESS_ROUTER"],
        })
        assert router["client_id"] is None and router["service_id"] is None

        contract = {"client_id": customer["id"], "site_id": first_site["id"], "plan_id": plan_record["id"],
                    "access_router_id": router["id"], "contracted_on": "2026-01-01"}
        pppoe = make(isp, "services", {
            **contract, "access_method": "PPPOE", "ip_assignment": "DYNAMIC", "pppoe_username": "cliente-1",
            "service_ip": "100.64.0.5", "access_mac": "02:00:00:00:00:01",
        })
        dhcp = make(isp, "services", {**contract, "site_id": second_site["id"], "access_method": "DHCP", "ip_assignment": "DYNAMIC"})
        fixed = make(isp, "services", {**contract, "access_method": "STATIC", "service_ip": "10.5.0.9", "monthly_price": "150"})
        assert fixed["ip_assignment"] == "FIXED" and float(fixed["monthly_price"]) == 150
        assert dhcp["access_method"] == "DHCP" and dhcp["service_ip"] is None
        assert pppoe["service_ip_text"] == "100.64.0.5" and pppoe["service_ip_observed_at"]
        assert request(isp, "POST", CRM + "services", {**contract, "access_method": "DHCP", "pppoe_username": "inválido"}).status_code == 422
        assert request(isp, "POST", CRM + "services", {**contract, "access_method": "PPPOE", "password": PASSWORD}).status_code == 422
        assert len(get(isp, "services", {"client_id": customer["id"]})["items"]) == 3
        assert len(get(isp, "services", {"site_id": second_site["id"]})["items"]) == 1
        assert get(isp, "infrastructure")["items"][0]["device_id"] == router["id"]

        device = make(isp, "devices", device_data(first_site, "192.168.10.2", "ONT de cliente", pppoe))
        assert device["client_id"] == customer["id"] and device["ip_address_text"] == "192.168.10.2"
        assert device["monitoring_state"] == "DISABLED"
        path = f"devices/{device['id']}/icmp"
        defaults = get(isp, path)
        assert {key: defaults[key] for key in ("packet_count", "timeout_ms", "interval_seconds", "failure_threshold", "recovery_threshold")} == {
            "packet_count": 5, "timeout_ms": 2000, "interval_seconds": 30, "failure_threshold": 3, "recovery_threshold": 2,
        }
        assert float(defaults["latency_warning_ms"]) == 200 and float(defaults["loss_failure_pct"]) == 30
        accepted(request(isp, "PUT", CRM + path, {"requested": True, "interval_seconds": 45, "packet_count": 6}))
        detail = get(isp, f"devices/{device['id']}")
        assert detail["monitoring_state"] == "UNKNOWN"
        assert detail["monitoring_enabled"] is False and detail["collector_id"] is None
        assert detail["config_revision"] > device["config_revision"]
        assert request(isp, "PUT", CRM + path, {"requested": True, "loss_warning_pct": 50, "loss_failure_pct": 30}).status_code == 422
        assert request(isp, "PUT", CRM + f"devices/{device['id']}", device_data(second_site, service=pppoe)).status_code == 422

        history_path = f"services/{pppoe['id']}/status"
        first = accepted(request(isp, "PATCH", CRM + history_path, {"status": "ACTIVE", "reason": "Instalación"}))
        activation = first["activated_at"]
        accepted(request(isp, "PATCH", CRM + history_path, {"status": "SUSPENDED", "reason": "Cambio manual"}))
        restored = accepted(request(isp, "PATCH", CRM + history_path, {"status": "ACTIVE", "reason": "Reactivado"}))
        assert activation == restored["activated_at"]
        accepted(request(isp, "PATCH", CRM + history_path, {"status": "CANCELLED", "reason": "Pedido del cliente"}))
        assert request(isp, "PATCH", CRM + history_path, {"status": "ACTIVE", "reason": "Cambio inválido"}).status_code == 409
        assert [item["new_status"] for item in get(isp, f"services/{pppoe['id']}/history")["items"]] == [
            "CANCELLED", "ACTIVE", "SUSPENDED", "ACTIVE", "PENDING",
        ]
        dashboard = get(isp, "dashboard")
        assert dashboard["clients"] == {"total": 1, "active": 1}
        assert dashboard["services"] == {"total": 3, "pending": 2, "active": 0, "suspended": 0}
        assert dashboard["devices"] == 2 and dashboard["sites"] == 3
        assert dashboard["distribution"][0]["total"] == 2 and dashboard["monitoring"] == {"available": False}
        events = accepted(admin.get("/api/v1/admin/audit", params={"company_id": company["company_id"]}))["items"]
        assert {"crm.client.create", "crm.internet_plan.create", "crm.device.icmp", "crm.service.status", "crm.site.create"} <= {e["action"] for e in events}
        assert "cliente-1" not in str(events)
        cookie = isp.cookies.get("sknet_isp")
    with TestClient(app) as restarted:
        reopened = accepted(restarted.get("/api/v1/" + CRM + f"devices/{device['id']}", headers={"Cookie": f"sknet_isp={cookie}"}))
        assert reopened["ip_address_text"] == "192.168.10.2" and reopened["monitoring_state"] == "UNKNOWN"
    assert migrated.execute("SELECT count(*) FROM connectivity.collectors").fetchone() == (0,)
    assert migrated.execute("SELECT count(*) FROM monitoring.icmp_checks").fetchone() == (0,)


def test_tenant_isolation_features_and_limits(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp, TestClient(app) as other, TestClient(app) as reader:
        authentication(admin)
        version = plan(admin, {**TERMS, "code": "CRM_LIMIT", "features": ["ACCESS", "CRM", "ICMP_CONFIG"],
                                 "max_clients": 1, "max_devices": 1, "max_users": 3, "min_poll_interval_seconds": 40})["versions"][0]["version_id"]
        settings(admin, False, version)
        registered = manual_signup(admin, "limite-crm")
        manual_signup(admin, "otro-crm")
        accepted(login(isp, "isp", "isp-limite-crm"))
        accepted(login(other, "isp", "isp-otro-crm"))
        a = make_client(isp)
        b = make_client(other, name="Otro cliente")
        assert request(isp, "POST", CRM + "clients", client_fields("EXTRA")).status_code == 409
        accepted(request(isp, "PATCH", CRM + f"clients/{a['id']}/status", SWITCH))
        assert request(isp, "POST", CRM + "clients", client_fields("EXTRA")).status_code == 409
        accepted(request(isp, "PATCH", CRM + f"clients/{a['id']}/status", {**SWITCH, "active": True}))
        first_site = make_site(isp, "Nodo A")
        second_site = make_site(other, "Nodo B")
        assert request(isp, "POST", CRM + "sites", {"client_id": b["id"], "site_type": "CLIENT_SITE", "name": "Ajeno"}).status_code == 404
        assert request(isp, "POST", CRM + "devices", device_data(second_site)).status_code == 404

        a_device = make(isp, "devices", device_data(first_site, "192.168.1.254"))
        b_device = make(other, "devices", device_data(second_site, "192.168.1.254"))
        valid = {"requested": True, "interval_seconds": 40}
        assert get(isp, f"devices/{a_device['id']}/icmp")["interval_seconds"] == 40
        assert request(isp, "PUT", CRM + f"devices/{a_device['id']}/icmp", {"requested": True}).status_code == 422
        accepted(request(isp, "PUT", CRM + f"devices/{a_device['id']}/icmp", valid))
        accepted(request(other, "PUT", CRM + f"devices/{b_device['id']}/icmp", valid))
        duplicate = make(isp, "devices", device_data(first_site, "192.168.1.254", "IP duplicada"))
        result = request(isp, "PUT", CRM + f"devices/{duplicate['id']}/icmp", valid)
        assert result.status_code == 409 and "IP de gestión" in result.text
        more = make(isp, "devices", device_data(first_site, "192.168.1.253", "Otro equipo"))
        assert request(isp, "PUT", CRM + f"devices/{more['id']}/icmp", valid).status_code == 409
        assert request(isp, "GET", CRM + f"devices/{b_device['id']}/icmp").status_code == 404
        assert [item["id"] for item in get(isp, "clients")["items"]] == [a["id"]]
        assert request(isp, "POST", CRM + "clients", {**client_fields("ZZZ"), "company_id": b["company_id"]}).status_code == 422
        assert admin.get("/api/v1/" + CRM + "clients").status_code == 401

        role = make_role(isp, "isp", "Consulta CRM", ["dashboard.read", "clients.read"])
        employee = accepted(request(isp, "POST", "isp/users", user_payload("lector-crm", [role])), 201)
        accepted(login(reader, "isp", "user-lector-crm", employee["temporary_password"]))
        accepted(change_password(reader, "isp", employee["temporary_password"]))
        assert set(get(reader, "dashboard")) == {"clients"}
        assert request(reader, "POST", CRM + "clients", client_fields("DENY")).status_code == 403
        assert request(reader, "GET", CRM + "devices").status_code == 403

        subscription = accepted(admin.get(f"/api/v1/admin/companies/{registered['company_id']}"))["subscription"]
        restricted = plan(admin, {**TERMS, "code": "NO_CRM", "features": ["ACCESS"]})["versions"][0]["version_id"]
        accepted(request(admin, "PUT", f"admin/subscriptions/{subscription['id']}", {
            "plan_version_id": restricted, "status": "ACTIVE", "reason": "Plan sin CRM",
        }))
        assert request(isp, "GET", CRM + "clients").status_code == 403
        assert get(isp, "dashboard") == {}


def test_migrate_crm_preserves_existing_records(database):
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "0004_platform")
    company = database.execute("INSERT INTO core.companies(name) VALUES ('Migración CRM') RETURNING id").fetchone()[0]
    cid = database.execute("""
        INSERT INTO crm.clients(company_id,client_code,name) VALUES (%s,'LEGACY','Cliente existente') RETURNING id
    """, (company,)).fetchone()[0]
    command.upgrade(config, "head")
    assert database.execute("SELECT name,observations FROM crm.clients WHERE id=%s", (cid,)).fetchone() == ("Cliente existente", None)
    assert database.execute("SELECT code FROM platform.features WHERE implemented AND code='ICMP'").fetchone() is None
