from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth.store import ISP, execute, row, rows
from app.crm import operations, schemas, store
from app.crm.classification import AccessMethod, DeviceCategory
from app.platform.routes import read, write


router = APIRouter(prefix=ISP.path + "/crm", tags=["CRM empresarial"])
Offset = Query(0, ge=0)
Limit = Query(30, ge=1, le=100)
Search = Query("", max_length=120)


def resource_routes(path, permission, resource, input_model):
    @router.get(path)
    def list_records(request: Request, q: str = Search, status: str | None = None, category: str | None = None,
                     client_id: UUID | None = None, site_id: UUID | None = None,
                     site_type: str | None = None, device_category: DeviceCategory | None = None,
                     isp_site: bool = False, eligible_for: AccessMethod | None = None, linkable_service: bool = False,
                     sort: Literal["name", "created", "status"] = "name",
                     direction: Literal["asc", "desc"] = "asc", offset: int = Offset, limit: int = Limit):
        with read(request, permission + ".read", ISP) as (db, actor):
            return store.listing(db, resource, actor.company, q=q, status=status, category=category,
                                 client=client_id, site=site_id, sort=sort, direction=direction, offset=offset, limit=limit,
                                 site_type=site_type, device_category=device_category, isp_site=isp_site,
                                 eligible_for=eligible_for, linkable_service=linkable_service)

    @router.get(path + "/{record_id}")
    def get_record(record_id: UUID, request: Request):
        with read(request, permission + ".read", ISP) as (db, actor):
            return store.details(db, resource, actor.company, record_id)

    @router.post(path, status_code=201)
    def create_record(data: input_model, request: Request):
        with write(request, permission + ".create", ISP) as (db, actor):
            return operations.save(db, actor, resource, data)

    @router.put(path + "/{record_id}")
    def edit_record(record_id: UUID, data: input_model, request: Request):
        with write(request, permission + ".write", ISP) as (db, actor):
            return operations.save(db, actor, resource, data, record_id)

    state_model = schemas.ServiceState if resource is store.SERVICES else schemas.State

    @router.patch(path + "/{record_id}/status")
    def update_status(record_id: UUID, data: state_model, request: Request):
        with write(request, permission + ".status", ISP) as (db, actor):
            if resource is store.SERVICES:
                return operations.service_status(db, actor, record_id, data)
            return operations.set_active(db, actor, resource, record_id, data)


resource_routes("/clients", "clients", store.CLIENTS, schemas.Client)
resource_routes("/internet-plans", "internet_plans", store.PLANS, schemas.InternetPlan)
resource_routes("/sites", "sites", store.SITES, schemas.Site)
resource_routes("/services", "services", store.SERVICES, schemas.Service)
resource_routes("/devices", "devices", store.DEVICES, schemas.Device)


@router.post("/clients/register", status_code=201)
def register_customer(data: schemas.Registration, request: Request):
    with write(request, "clients.create", ISP) as (db, actor):
        return operations.register_customer(db, actor, data)


def child_routes(path, table, entity, input_model, *, append_only=False):
    endpoint = "/clients/{client_id}" + path

    @router.get(endpoint)
    def list_entries(client_id: UUID, request: Request, offset: int = Offset, limit: int = Limit):
        with read(request, "clients.read", ISP) as (db, actor):
            store.owned(db, "clients", actor.company, client_id)
            if table == store.NOTES:
                select = """
                    n.*, u.name AS author FROM crm.client_notes n
                    JOIN core.memberships m ON m.company_id=n.company_id AND m.id=n.author_id
                    JOIN core.users u ON u.id=m.user_id
                """
                ordering = "n.created_at DESC,n.id"
            else:
                select = f"n.* FROM crm.{table} n"
                ordering = "n.is_primary DESC,lower(n.name),n.id" if table == store.CONTACTS else "lower(n.address),n.id"
            values = rows(db, f"""
                SELECT {select} WHERE n.company_id=:company AND n.client_id=:client
                ORDER BY {ordering} OFFSET :offset LIMIT :limit
            """, company=actor.company, client=client_id, offset=offset, limit=limit + 1)
            return {"items": values[:limit], "has_more": len(values) > limit}

    def save_entry(db, actor, client_id, data, record_id=None):
        store.owned(db, "clients", actor.company, client_id)
        previous = None
        if record_id:
            previous = row(db, f"SELECT * FROM crm.{table} WHERE company_id=:company AND client_id=:client AND id=:id",
                           company=actor.company, client=client_id, id=record_id)
            if previous is None:
                raise HTTPException(404, "Registro no encontrado para este cliente.")
        values = data.model_dump()
        if table == store.NOTES:
            values["author_id"] = actor.user["person_id"]
        if table == store.CONTACTS and values["is_primary"]:
            cleared = rows(db, """
                UPDATE crm.client_contacts SET is_primary=false
                WHERE company_id=:company AND client_id=:client AND is_primary AND id IS DISTINCT FROM CAST(:id AS uuid)
                RETURNING id
            """, company=actor.company, client=client_id, id=record_id)
            for contact in cleared:
                store.change_event(db, actor, entity, contact["id"], "update",
                                   {"is_primary": True}, {"is_primary": False}, client=client_id)
        if record_id:
            store.update(db, table, actor.company, record_id, values)
        else:
            record_id = store.insert(db, table, actor.company, {**values, "client_id": client_id})
        store.change_event(db, actor, entity, record_id, "update" if previous else "create",
                           {key: previous[key] for key in values} if previous else None, values, client=client_id)
        return store.owned(db, table, actor.company, record_id)

    @router.post(endpoint, status_code=201)
    def create_entry(client_id: UUID, data: input_model, request: Request):
        with write(request, "clients.write", ISP) as (db, actor):
            return save_entry(db, actor, client_id, data)

    if not append_only:
        @router.put(endpoint + "/{record_id}")
        def update_entry(client_id: UUID, record_id: UUID, data: input_model, request: Request):
            with write(request, "clients.write", ISP) as (db, actor):
                return save_entry(db, actor, client_id, data, record_id)


child_routes("/contacts", store.CONTACTS, "contact", schemas.Contact)
child_routes("/addresses", store.ADDRESSES, "address", schemas.Address)
child_routes("/notes", store.NOTES, "client_note", schemas.ClientNote, append_only=True)


@router.get("/services/{record_id}/history")
def service_history(record_id: UUID, request: Request, offset: int = Offset, limit: int = Limit):
    with read(request, "services.read", ISP) as (db, actor):
        actor.require("crm_history.read")
        return operations.state_history(db, actor.company, record_id, offset, limit)


@router.get("/{section}/{record_id}/activity")
def activity(section: Literal["clients", "devices"], record_id: UUID, request: Request,
             offset: int = Offset, limit: int = Limit):
    with read(request, "crm_history.read", ISP) as (db, actor):
        actor.require(section + ".read")
        resource = store.CLIENTS if section == "clients" else store.DEVICES
        store.owned(db, resource.table, actor.company, record_id)
        return store.history(db, actor.company, resource, record_id, offset, limit)


@router.get("/devices/{record_id}/icmp")
def get_icmp(record_id: UUID, request: Request):
    with read(request, "icmp.read", ISP) as (db, actor):
        actor.require("devices.read")
        config = operations.profile(db, actor.company, record_id)
        if not config["configured"] and actor.plan["min_poll_interval_seconds"]:
            config["interval_seconds"] = max(config["interval_seconds"], actor.plan["min_poll_interval_seconds"])
        return {**config, "minimum_interval_seconds": actor.plan["min_poll_interval_seconds"] or 5}


@router.put("/devices/{record_id}/icmp")
def put_icmp(record_id: UUID, data: schemas.IcmpProfile, request: Request):
    with write(request, "icmp.write", ISP) as (db, actor):
        actor.require("devices.read")
        return operations.save_profile(db, actor, record_id, data)


@router.get("/infrastructure")
def infrastructure(request: Request, q: str = Search, role: schemas.Role | None = None,
                   offset: int = Offset, limit: int = Limit):
    with read(request, "infrastructure.read", ISP) as (db, actor):
        data = rows(db, """
            SELECT s.id AS site_id,s.name AS site_name,s.site_type,s.active AS site_active,
                   d.id AS device_id,d.name AS device_name,d.device_role,
                   d.administrative_active AND d.retired_at IS NULL AS device_active
            FROM crm.sites s LEFT JOIN crm.devices d ON d.company_id=s.company_id AND d.site_id=s.id
            WHERE s.company_id=:company AND s.site_category IN ('NETWORK','FACILITY')
              AND (CAST(:role AS text) IS NULL OR d.device_role=:role)
              AND strpos(lower(concat_ws(' ',s.name,d.name)),lower(:q))>0
            ORDER BY lower(s.name),lower(d.name),s.id,d.id OFFSET :offset LIMIT :limit
        """, company=actor.company, role=role, q=q.strip(), offset=offset, limit=limit + 1)
        return {"items": data[:limit], "has_more": len(data) > limit}


@router.get("/dashboard")
def dashboard(request: Request):
    with read(request, "dashboard.read", ISP) as (db, actor):
        permissions = actor.permissions
        result = {}
        if "clients.read" in permissions:
            result["clients"] = row(db, """
                SELECT count(*) AS total,count(*) FILTER (WHERE status='ACTIVE') AS active
                FROM crm.clients WHERE company_id=:company
            """, company=actor.company)
        if "services.read" in permissions:
            result["services"] = row(db, """
                SELECT count(*) AS total,count(*) FILTER (WHERE status='ACTIVE') AS active,
                       count(*) FILTER (WHERE status='PENDING') AS pending,
                       count(*) FILTER (WHERE status='SUSPENDED') AS suspended
                FROM crm.services WHERE company_id=:company
            """, company=actor.company)
            if "internet_plans.read" in permissions:
                result["distribution"] = rows(db, """
                    SELECT p.id,p.name,count(*) AS total FROM crm.services s
                    JOIN crm.service_plans p ON p.company_id=s.company_id AND p.id=s.plan_id
                    WHERE s.company_id=:company AND s.status<>'CANCELLED'
                    GROUP BY p.id,p.name ORDER BY total DESC,p.id
                """, company=actor.company)
        for permission, table in (("sites.read", "sites"), ("devices.read", "devices")):
            if permission in permissions:
                result[table] = execute(db, f"SELECT count(*) FROM crm.{table} WHERE company_id=:company",
                                        company=actor.company).scalar_one()
        if "icmp.read" in permissions and "devices.read" in permissions:
            result["monitoring"] = {"available": False}
        if "crm_history.read" in permissions:
            allowed = {
                "clients.read": ["client", "contact", "address", "client_note"], "internet_plans.read": ["internet_plan"],
                "services.read": ["service"], "sites.read": ["site"], "devices.read": ["device"],
            }
            entities = [entity for permission, group in allowed.items() if permission in permissions for entity in group]
            result["activity"] = rows(db, """
                SELECT e.id,e.occurred_at,e.action,e.entity_type,e.entity_id,u.name AS actor
                FROM audit.events e LEFT JOIN core.users u ON u.id=e.actor_user_id
                WHERE e.company_id=:company AND starts_with(e.action,'crm.') AND e.entity_type=ANY(:entities)
                  AND (:icmp OR e.action<>'crm.device.icmp')
                ORDER BY e.occurred_at DESC,e.id LIMIT 8
            """, company=actor.company, entities=entities, icmp="icmp.read" in permissions)
        return result
