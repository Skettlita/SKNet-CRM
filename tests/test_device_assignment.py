from fastapi.testclient import TestClient

from app.main import app
from test_access import admin_id, login, migrated, request
from test_crm import CRM, get, make, make_plan
from test_platform import accepted, authentication, manual_signup


def test_available_equipment_reassignment_and_inherited_ip(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        manual_signup(admin, "asignacion")
        accepted(login(isp, "isp", "isp-asignacion"))
        equip = make(isp, "devices", {"name": "ONT disponible", "device_type": "ONT", "device_role": "ENDPOINT",
                                     "device_category": "CUSTOMER_EQUIPMENT", "ownership": "ISP"})
        assert (equip["assignment_state"], equip["site_id"], equip["effective_ip"]) == ("AVAILABLE", None, None)
        assert get(isp, "devices", {"assignment_state": "AVAILABLE"})["items"][0]["id"] == equip["id"]
        client = make(isp, "clients", {"name": "Abonado QA", "client_type": "PERSON"})
        site = make(isp, "sites", {"name": "Casa QA", "site_type": "HOME", "client_id": client["id"]})
        terms = {"client_id": client["id"], "site_id": site["id"], "plan_id": make_plan(isp)["id"], "access_method": "PPPOE"}
        service = make(isp, "services", terms | {"service_ip": "192.168.10.10"})
        path = "devices/" + equip["id"]
        placed = accepted(request(isp, "POST", CRM + path + "/assignment", {
            "site_id": site["id"], "service_id": service["id"], "assignment_state": "INSTALLED",
            "ip_mode": "SERVICE", "reason": "Instalación histórica",
        }))
        assert placed["effective_ip"] == "192.168.10.10" and placed["ip_address_text"] is None
        accepted(request(isp, "PUT", CRM + path + "/icmp", {"requested": True}))
        revision = get(isp, path)["config_revision"]
        accepted(request(isp, "PUT", CRM + "services/" + service["id"], terms | {"service_ip": "192.168.10.55"}))
        assert get(isp, path)["effective_ip"] == "192.168.10.55"
        assert get(isp, path)["config_revision"] == revision + 1
        accepted(request(isp, "PUT", CRM + "services/" + service["id"], terms))
        assert get(isp, path)["effective_ip"] is None
        accepted(request(isp, "POST", CRM + path + "/assignment", {
            "assignment_state": "AVAILABLE", "ip_mode": "NONE", "reason": "Retiro de la ubicación",
        }))
        assert get(isp, path)["site_id"] is None
        history = get(isp, path + "/assignments")["items"]
        assert [row["current_data"]["assignment_state"] for row in history] == ["AVAILABLE", "INSTALLED"]
        assert request(isp, "DELETE", CRM + path, {"confirmed": True, "reason": "Error"}).status_code == 409
