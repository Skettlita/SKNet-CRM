from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from test_access import admin_id, login, migrated, request
from test_crm import CRM, get, make_plan
from test_crm_workflow import customer, initial
from test_platform import accepted, authentication, manual_signup


BASE = "isp/inventory/"


def catalog(isp, path, fields):
    return accepted(request(isp, "POST", BASE+"catalog/"+path, fields), 201)


def test_inventory_batches_and_atomic_assignment(migrated, admin_id):
    with TestClient(app) as admin, TestClient(app) as isp, TestClient(app) as other:
        authentication(admin)
        for operator, name in ((isp, "stock"), (other, "otro-stock")):
            manual_signup(admin, name)
            accepted(login(operator, "isp", "isp-"+name))
        kind = catalog(isp, "types", {"name": "Router"})
        brand = catalog(isp, "manufacturers", {"name": "Fabricante QA"})
        model = catalog(isp, "models", {"name": "Modelo QA", "type_id": kind["id"], "manufacturer_id": brand["id"]})
        assert request(isp, "POST", BASE+"catalog/manufacturers", {"name": "fabricante   qa"}).status_code == 409
        assert accepted(request(other, "GET", BASE+"catalog/models"))["items"] == []
        payload = {"model_id": model["id"], "device_category": "CUSTOMER_EQUIPMENT", "quantity": 20, "ownership": "ISP"}
        batch = accepted(request(isp, "POST", BASE+"stock/batches", payload), 201)["items"]
        assert len(batch) == len({device["device_code"] for device in batch}) == 20
        assert request(other, "POST", BASE+"stock/batches", payload).status_code == 422
        assert accepted(request(isp, "GET", BASE+"stock"))["items"][0]["available"] == 20
        assert request(isp, "DELETE", BASE+"catalog/models/"+model["id"]).status_code == 409

        plan = make_plan(isp)
        initial_fields = initial(plan)
        initial_fields["site"].pop("name")
        result = accepted(request(isp, "POST", CRM+"clients/register", customer("Abonado automático") | initial_fields |
                                  {"equipment": {"model_id": model["id"]}}), 201)
        assert result["site"]["name"] == result["client"]["client_code"]
        assert result["equipment"]["assignment_state"] == "ASSIGNED" and result["service"]["status"] == "PENDING"
        assert result["equipment"]["service_id"] == result["service"]["id"]
        assert result["installation"] is None

        available = get(isp, "devices", {"assignment_state": "AVAILABLE"})["items"][0]
        def assign(index):
            return request(isp, "POST", CRM+"clients/register", customer(f"Abonado concurrente {index}") | initial_fields |
                           {"equipment": {"device_id": available["id"]}})
        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(assign, (1, 2)))
        assert sorted(result.status_code for result in outcomes) == [201, 409]
        assert len(get(isp, "clients")["items"]) == 2
        assert accepted(request(isp, "GET", BASE+"stock"))["items"][0]["available"] == 18
        assert request(isp, "POST", CRM+"devices", {"name": "Texto libre", "device_type": "No definido",
                                                   "device_role": "ENDPOINT", "device_category": "CUSTOMER_EQUIPMENT"}).status_code == 422
