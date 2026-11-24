from concurrent.futures import ThreadPoolExecutor

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import app
from test_access import admin_id, change_password, login, make_role, migrated, request, user_payload
from test_crm import CRM, get, make, make_plan
from test_migrations import BACKEND
from test_platform import accepted, authentication, manual_signup


def customer(name):
    return {"client_type": "PERSON", "name": name}


def initial(plan, *, router=None, situation="UNDEFINED"):
    return {
        "site": {"name": "Domicilio inicial", "site_type": "HOME", "use_client_address": True,
                 "latitude": "-16.5", "longitude": "-68.15"},
        "address": {"address": "Calle principal 120", "city": "La Paz"},
        "service": {"plan_id": plan["id"], "access_method": "PPPOE", "access_router_id": router,
                    "pppoe_username": "cuenta-abonado", "service_ip": "172.16.10.21"},
        "installation_situation": situation,
    }


def network_equipment(client, site, name, capabilities=()):
    return make(client, "devices", {
        "name": name, "site_id": site["id"], "device_role": "NODE", "device_type": "Router",
        "device_category": "INFRASTRUCTURE", "capabilities": list(capabilities),
        "serial_number": "SKU-101", "mac_address": "12:ab:34:cd:56:ef",
    })


def test_integrated_customer_initial_states_and_rollback(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        manual_signup(admin, "alta")
        accepted(login(isp, "isp", "isp-alta"))
        plan = make_plan(isp)
        solo = make(isp, "clients/register", customer("Sin contrato"))
        assert solo["client"]["client_code"] == "CLI-000001"
        assert solo["site"] is None and solo["service"] is None
        fields = customer("Conectado") | initial(plan, situation="EXISTING")
        result = make(isp, "clients/register", fields)
        client, site, service = (result[name] for name in ("client", "site", "service"))
        assert (client["client_code"], site["site_code"], service["service_code"]) == ("CLI-000002", "SIT-000001", "SRV-000001")
        assert site["name"] == "Domicilio inicial" and site["client_id"] == client["id"]
        assert site["address"] is None and site["effective_address"] == "Calle principal 120"
        assert service["status"] == "ACTIVE" and service["activated_at"] and service["installation_situation"] == "EXISTING"
        assert (service["monthly_price"], service["currency"], service["service_ip_text"]) == (160.50, "BOB", "172.16.10.21")
        assert get(isp, f"services/{service['id']}/history")["items"][0]["new_status"] == "ACTIVE"
        address = get(isp, f"clients/{client['id']}/addresses")["items"][0]
        updated = {"address": "Dirección corregida", "city": "El Alto"}
        accepted(request(isp, "PUT", CRM + f"clients/{client['id']}/addresses/{address['id']}", updated))
        assert get(isp, f"sites/{site['id']}")["effective_address"] == "Dirección corregida"

        failed = initial(plan, router=client["id"])
        assert request(isp, "POST", CRM + "clients/register", customer("Transacción fallida") | failed).status_code == 404
        assert not get(isp, "clients", {"q": "Transacción fallida"})["items"]
        assert migrated.execute("SELECT count(*) FROM crm.client_addresses").fetchone() == (1,)
        assert migrated.execute("SELECT count(*) FROM crm.sites").fetchone() == (1,)
        assert migrated.execute("SELECT count(*) FROM crm.services").fetchone() == (1,)
        assert migrated.execute("SELECT count(*) FROM audit.events WHERE after_data->>'name'='Transacción fallida'").fetchone() == (0,)

        modified = initial(plan, situation="NEW")
        modified["site"].update(use_client_address=False, address="Otra ubicación", site_type="BRANCH")
        modified["service"]["monthly_price"] = "115.25"
        pending = make(isp, "clients/register", customer("Instalación nueva") | modified)
        assert pending["client"]["client_code"] == "CLI-000003"
        assert pending["site"]["site_code"] == "SIT-000002" and pending["site"]["effective_address"] == "Otra ubicación"
        assert pending["service"]["monthly_price"] == 115.25 and pending["service"]["status"] == "PENDING"
        assert pending["service"]["installation_situation"] == "NEW"
        unfixed = make(isp, "clients/register", customer("Por definir") | initial(plan))
        assert unfixed["service"]["status"] == "PENDING" and unfixed["service"]["installation_situation"] == "UNDEFINED"


def test_sites_devices_service_choices_and_ownership(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp, TestClient(app) as foreign:
        authentication(admin)
        for client, company in ((isp, "equipos"), (foreign, "ajeno")):
            manual_signup(admin, company)
            accepted(login(client, "isp", "isp-" + company))
        plan = make_plan(isp)
        hub = make(isp, "sites", {"name": "Central metropolitana", "site_type": "MAIN_NODE", "site_category": "NETWORK"})
        warehouse = make(isp, "sites", {"name": "Depósito", "site_type": "WAREHOUSE", "site_category": "FACILITY"})
        router = network_equipment(isp, hub, "Servidor compartido", ("PPPOE_SERVER", "DISTRIBUTION"))
        dhcp = network_equipment(isp, hub, "DHCP dedicado", ("DHCP_SERVER",))
        assert router["device_code"] == "DSP-000001" and router["client_id"] is None and router["service_id"] is None
        assert router["serial_number"] == "SKU-101"
        assert get(isp, "sites", {"isp_site": True})["items"]
        first = make(isp, "clients/register", customer("Abonado Primero") | initial(plan, router=router["id"]))
        client, site, service = (first[name] for name in ("client", "site", "service"))
        branch = make(isp, "sites", {"name": "Sucursal secundaria", "site_type": "BRANCH", "client_id": client["id"]})
        contract = {"client_id": client["id"], "site_id": branch["id"], "plan_id": plan["id"], "access_method": "PPPOE"}
        alternate = make(isp, "services", contract | {"access_router_id": router["id"]})
        assert alternate["access_router_id"] == service["access_router_id"] == router["id"]
        assert len(get(isp, "services", {"client_id": client["id"]})["items"]) == 2
        assert len(get(isp, "sites", {"client_id": client["id"]})["items"]) == 2
        assert request(isp, "POST", CRM + "services", contract | {"access_router_id": dhcp["id"]}).status_code == 422

        endpoint_data = {"name": "ONT doméstica", "site_id": site["id"], "client_id": client["id"], "device_role": "ENDPOINT",
                         "device_type": "ONT", "device_category": "CUSTOMER_EQUIPMENT", "ip_address": "192.168.5.123"}
        endpoint = make(isp, "devices", endpoint_data)
        assigned = make(isp, "devices", endpoint_data | {"name": "Router Wi-Fi", "service_id": service["id"]})
        assert endpoint["service_id"] is None and assigned["service_id"] == service["id"]
        assert endpoint["ip_address_text"] != service["service_ip_text"]
        assert len(get(isp, "devices", {"client_id": client["id"]})["items"]) == 2
        assert request(isp, "POST", CRM + "devices", endpoint_data | {"service_id": alternate["id"]}).status_code == 422
        assert request(isp, "POST", CRM + "devices", endpoint_data | {"site_id": hub["id"]}).status_code == 422
        assert request(isp, "POST", CRM + "devices", endpoint_data | {"capabilities": ["PPPOE_SERVER"]}).status_code == 422
        assert request(isp, "POST", CRM + "services", contract | {"access_router_id": endpoint["id"]}).status_code == 422
        assert not get(isp, "devices", {"eligible_for": "PPPOE", "q": "Router Wi-Fi"})["items"]
        assert [record["id"] for record in get(isp, "devices", {"eligible_for": "PPPOE"})["items"]] == [router["id"]]
        accepted(request(isp, "PATCH", CRM + f"devices/{router['id']}/status", {"active": False, "reason": "Mantenimiento"}))
        assert not get(isp, "devices", {"eligible_for": "PPPOE"})["items"]
        assert request(isp, "POST", CRM + "services", contract | {"access_router_id": router["id"]}).status_code == 409

        other = make(foreign, "clients", customer("Cliente externo"))
        assert other["client_code"] == "CLI-000001"
        other_site = make(foreign, "sites", {"name": "Otra empresa", "site_type": "HOME", "client_id": other["id"]})
        assert request(isp, "POST", CRM + "devices", endpoint_data | {"site_id": other_site["id"]}).status_code == 404
        assert request(isp, "POST", CRM + "services", contract | {"client_id": other["id"]}).status_code == 404
        assert request(isp, "PUT", CRM + f"sites/{site['id']}", {"name": "Propia", "site_type": "WAREHOUSE"}).status_code == 409

        page = get(isp, "sites", {"category": "CUSTOMER", "q": "Abonado Primero", "limit": 1})
        assert page["has_more"] and len(page["items"]) == 1
        assert get(isp, "sites", {"category": "CUSTOMER", "q": "Abonado Primero", "limit": 1, "offset": 1})["items"][0]["id"] != page["items"][0]["id"]
        assert [item["id"] for item in get(isp, "sites", {"category": "FACILITY", "site_type": "WAREHOUSE", "q": warehouse["site_code"]})["items"]] == [warehouse["id"]]
        assert {item["id"] for item in get(isp, "sites", {"isp_site": True, "sort": "created", "direction": "desc"})["items"]} == {hub["id"], warehouse["id"]}


def test_concurrent_codes_and_integrated_permissions(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp, TestClient(app) as clerk:
        authentication(admin)
        manual_signup(admin, "concurrente")
        accepted(login(isp, "isp", "isp-concurrente"))
        plan = make_plan(isp)

        def register(index):
            return make(isp, "clients/register", customer(f"Cliente {index}") | initial(plan))
        with ThreadPoolExecutor(max_workers=5) as executor:
            created = list(executor.map(register, range(8)))
        for entity, prefix in (("client", "CLI"), ("site", "SIT"), ("service", "SRV")):
            assert {data[entity][entity + "_code"] for data in created} == {f"{prefix}-{value:06d}" for value in range(1, 9)}
        hub = make(isp, "sites", {"name": "Central", "site_type": "MAIN_NODE"})
        with ThreadPoolExecutor(max_workers=4) as executor:
            equipment = list(executor.map(lambda index: network_equipment(isp, hub, f"Equipo {index}"), range(4)))
        assert {record["device_code"] for record in equipment} == {f"DSP-{value:06d}" for value in range(1, 5)}

        role = make_role(isp, "isp", "Alta limitada", ["clients.read", "clients.create"])
        employee = accepted(request(isp, "POST", "isp/users", user_payload("alta-limitada", [role])), 201)
        accepted(login(clerk, "isp", "user-alta-limitada", employee["temporary_password"]))
        accepted(change_password(clerk, "isp", employee["temporary_password"]))
        assert request(clerk, "POST", CRM + "clients/register", customer("Sin permiso") | initial(plan)).status_code == 403
        assert make(clerk, "clients/register", customer("Alta autorizada"))["client"]["client_code"] == "CLI-000009"
        assert not get(isp, "clients", {"q": "Sin permiso"})["items"]
        # A committed code remains reserved even if an administrator removes the record outside the application.
        migrated.execute("DELETE FROM crm.clients WHERE client_code='CLI-000009'")
        assert make(isp, "clients", customer("Alta posterior"))["client_code"] == "CLI-000010"

        migrated.execute("""
            INSERT INTO core.role_permissions(company_id,role_id,permission_id)
            SELECT r.company_id,r.id,p.id FROM core.roles r CROSS JOIN core.permissions p
            WHERE r.id=%s AND p.code IN ('services.create','sites.create','installations.create')
        """, (role,))
        assert request(clerk, "POST", CRM + "clients/register", customer("Activación restringida") |
                       initial(plan, situation="EXISTING")).status_code == 403
        assert make(clerk, "clients/register", customer("Servicio pendiente") | initial(plan, situation="NEW"))["service"]["status"] == "PENDING"


def test_migration_assigns_codes_and_preserves_prior_associations(database):
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "0006_connectivity")
    company = database.execute("INSERT INTO core.companies(name) VALUES ('Anterior') RETURNING id").fetchone()[0]
    client = database.execute("""
        INSERT INTO crm.clients(company_id,client_code,name) VALUES (%s,'CLI-000075','Abonado anterior') RETURNING id
    """, (company,)).fetchone()[0]
    customer_site = database.execute("""
        INSERT INTO crm.sites(company_id,client_id,name,site_type,address)
        VALUES (%s,%s,'Sitio anterior','CLIENT_SITE','Dirección anterior') RETURNING id
    """, (company, client)).fetchone()[0]
    site = database.execute("""
        INSERT INTO crm.sites(company_id,name,site_type) VALUES (%s,'Ubicación ambigua','NODE') RETURNING id
    """, (company,)).fetchone()[0]
    device = database.execute("""
        INSERT INTO crm.devices(company_id,site_id,name,device_type,device_role,serial_number)
        VALUES (%s,%s,'Router anterior','Router','INTERMEDIATE','SN anterior') RETURNING id
    """, (company, site)).fetchone()[0]
    plan = database.execute("""
        INSERT INTO crm.service_plans(company_id,name,service_type,monthly_price)
        VALUES (%s,'Plan anterior','INTERNET',100) RETURNING id
    """, (company,)).fetchone()[0]
    service = database.execute("""
        INSERT INTO crm.services(company_id,client_id,site_id,plan_id,monthly_price,access_method,access_router_id,status)
        VALUES (%s,%s,%s,%s,100,'PPPOE',%s,'ACTIVE') RETURNING id
    """, (company, client, customer_site, plan, device)).fetchone()[0]
    command.upgrade(config, "head")
    assert database.execute("SELECT client_code FROM crm.clients WHERE id=%s", (client,)).fetchone() == ("CLI-000075",)
    assert database.execute("SELECT last_number FROM crm.commercial_counters WHERE company_id=%s AND entity='client'", (company,)).fetchone() == (75,)
    assert database.execute("SELECT site_type,site_category,address FROM crm.sites WHERE id=%s", (customer_site,)).fetchone() == (
        "CUSTOMER_OTHER", "CUSTOMER", "Dirección anterior",
    )
    assert database.execute("SELECT site_type,site_category FROM crm.sites WHERE id=%s", (site,)).fetchone() == ("NETWORK_OTHER", "NETWORK")
    assert database.execute("SELECT device_code,device_category,device_role,serial_number,capabilities FROM crm.devices WHERE id=%s", (device,)).fetchone() == (
        "DSP-000001", "INFRASTRUCTURE", "INTERMEDIATE", "SN anterior", ["PPPOE_SERVER"],
    )
    assert database.execute("SELECT service_code,access_router_id,status FROM crm.services WHERE id=%s", (service,)).fetchone() == ("SRV-000001", device, "ACTIVE")
