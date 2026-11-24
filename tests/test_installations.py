from fastapi.testclient import TestClient

from app.main import app
from test_access import admin_id, login, migrated, request
from test_crm import CRM, get, make, make_plan
from test_crm_workflow import customer, initial
from test_platform import accepted, authentication, manual_signup


def test_installation_order_activation_and_cancellation(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        manual_signup(admin, "instalaciones")
        accepted(login(isp, "isp", "isp-instalaciones"))
        plan = make_plan(isp)
        entry = make(isp, "clients/register", customer("Alta con orden") | initial(plan, situation="NEW"))
        order = entry["installation"]
        svc = entry["service"]
        assert order["installation_code"] == "INS-000001" and svc["status"] == "PENDING"
        order_path = CRM + "installations/" + order["id"]
        assert request(isp, "POST", CRM+"installations", {"service_id": svc["id"], "reason": "Duplicada"}).status_code == 409
        technician = get(isp, "installations/technicians")[0]["id"]
        accepted(request(isp, "PUT", order_path, {"technician_ids": [technician], "observations": "Confirmado"}))
        assert get(isp, order_path.removeprefix(CRM))["technicians"][0]["id"] == technician
        assert request(isp, "POST", order_path+"/status", {"status": "COMPLETED", "reason": "Error"}).status_code == 409
        for when in ("2027-01-02T14:00:00Z", "2027-01-03T14:00:00Z"):
            accepted(request(isp, "POST", order_path+"/status", {"status": "SCHEDULED", "reason": "Programación", "scheduled_at": when}))
        device = accepted(request(isp, "POST", order_path+"/devices", {
            "new_device": {"name": "ONT nueva", "device_type": "ONT"}, "link_service": True, "ip_mode": "SERVICE", "reason": "Asignación",
        }), 201)
        assert device["assignment_state"] == "ASSIGNED" and device["effective_ip"] == "172.16.10.21"
        accepted(request(isp, "POST", order_path+"/status", {"status": "IN_PROGRESS", "reason": "Inicio"}))
        assert request(isp, "POST", order_path+"/status", {"status": "COMPLETED", "reason": "Prueba"}).status_code == 422
        assert get(isp, "services/"+svc["id"])["status"] == "PENDING"
        completed = accepted(request(isp, "POST", order_path+"/status", {
            "status": "COMPLETED", "reason": "Lista", "verification": "Prueba manual completa", "monitor_devices": [device["id"]],
        }))
        assert completed["completed_at"] and get(isp, "services/"+svc["id"])["status"] == "ACTIVE"
        actual = get(isp, "devices/"+device["id"])
        assert actual["assignment_state"] == "INSTALLED" and actual["monitoring_requested"]
        assert get(isp, order_path.removeprefix(CRM))["history"][0]["new_status"] == "COMPLETED"
        assert request(isp, "DELETE", order_path, {"confirmed": True, "reason": "Eliminar"}).status_code == 409

        existing = make(isp, "clients/register", customer("Servicio existente") | initial(plan, situation="EXISTING"))
        assert existing["installation"] is None and existing["service"]["status"] == "ACTIVE"
        pending = make(isp, "clients/register", customer("Definir luego") | initial(plan))
        assert pending["installation"] is None
        later = make(isp, "installations", {"service_id": pending["service"]["id"], "reason": "Crear borrador"})
        later_path = CRM + "installations/" + later["id"]
        assert request(isp, "DELETE", later_path, {"confirmed": True, "reason": "Borrador"}).status_code == 204
        later = make(isp, "installations", {"service_id": pending["service"]["id"], "reason": "Posterior"})
        assert later["installation_code"] == "INS-000003"
        accepted(request(isp, "POST", CRM+"installations/"+later["id"]+"/status", {"status": "CANCELLED", "reason": "Cancelación"}))
        assert get(isp, "services/"+pending["service"]["id"])["status"] == "PENDING"
        assert len(get(isp, "installations", {"status": "CANCELLED"})["items"]) == 1
