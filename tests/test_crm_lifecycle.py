from fastapi.testclient import TestClient

from app.main import app
from test_access import admin_id, login, migrated, request
from test_crm import CRM, get, make, make_plan
from test_platform import accepted, authentication, manual_signup


def test_confirmed_delete_archive_and_field_errors(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        manual_signup(admin, "ciclo")
        accepted(login(isp, "isp", "isp-ciclo"))
        fields = {"client_type": "PERSON", "name": "Alta equivocada"}
        entry = make(isp, "clients", fields)
        path = CRM + "clients/" + entry["id"]
        assert request(isp, "DELETE", path, {"confirmed": False, "reason": "Error"}).status_code == 422
        assert request(isp, "DELETE", path, {"confirmed": True, "reason": "Error"}).status_code == 204
        assert request(isp, "GET", path).status_code == 404
        entry = make(isp, "clients", fields)
        assert entry["client_code"] == "CLI-000002"
        path = CRM + "clients/" + entry["id"]
        make(isp, "sites", {"site_type": "HOME", "client_id": entry["id"], "name": "Casa"})
        denied = request(isp, "DELETE", path, {"confirmed": True, "reason": "Error"})
        assert denied.status_code == 409 and denied.json()["detail"]["dependencies"] == ["sitios"]
        accepted(request(isp, "POST", path + "/archive", {"reason": "Conservar historial"}))
        assert get(isp, "clients")["items"] == []
        assert get(isp, "clients", {"status": "ARCHIVED"})["items"][0]["id"] == entry["id"]
        assert request(isp, "PATCH", path + "/status", {"active": True, "reason": "Reactivar"}).status_code == 409
        bad = request(isp, "POST", CRM + "sites", {"name": "Fuera de rango", "site_type": "MAIN_NODE",
                                                "latitude": "93.0", "longitude": "-69"})
        assert bad.status_code == 422 and "latitude" in bad.json()["fields"]
        pair = request(isp, "POST", CRM + "sites", {"name": "Falta dato", "site_type": "MAIN_NODE", "latitude": "-3"})
        assert pair.status_code == 422 and "longitude" in pair.json()["fields"]


def test_delete_service_with_only_initial_history(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp:
        authentication(admin)
        manual_signup(admin, "delete-service")
        accepted(login(isp, "isp", "isp-delete-service"))
        client = make(isp, "clients", {"client_type": "PERSON", "name": "Servicio QA"})
        site = make(isp, "sites", {"site_type": "HOME", "client_id": client["id"], "name": "Casa"})
        plan = make_plan(isp)
        fields = {"client_id": client["id"], "site_id": site["id"], "plan_id": plan["id"],
                  "access_method": "DHCP", "initial_status": "ACTIVE"}
        record = make(isp, "services", fields)
        assert record["status"] == "ACTIVE"
        assert request(isp, "DELETE", CRM+"services/"+record["id"],
                       {"confirmed": True, "reason": "Alta duplicada"}).status_code == 204
        kept = make(isp, "services", fields)
        migrated.execute("""
            INSERT INTO crm.service_status_history(company_id,service_id,previous_status,new_status)
            SELECT company_id,id,'SUSPENDED','ACTIVE' FROM crm.services WHERE id=%s
        """, (kept["id"],))
        blocked = request(isp, "DELETE", CRM+"services/"+kept["id"], {"confirmed": True, "reason": "Alta duplicada"})
        assert blocked.status_code == 409 and "historial de estados" in blocked.json()["detail"]["dependencies"]
