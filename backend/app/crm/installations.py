from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AwareDatetime, Field, model_validator

from app.auth.schemas import Input, Name
from app.auth.store import ISP, execute, row, rows
from app.crm import lifecycle, operations, schemas, store
from app.platform.routes import read, write
from app.validation import problem


router = APIRouter(prefix=ISP.path + "/crm/installations", tags=["Instalaciones"])
TERMINAL = {"COMPLETED", "CANCELLED"}
TRANSITIONS = {
    "PENDING": {"SCHEDULED", "IN_PROGRESS", "CANCELLED"},
    "SCHEDULED": {"SCHEDULED", "IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
}
ORDERS = store.Resource("installations", "installation", "t.installation_code", "", "t.status")
SELECT = """
    SELECT i.*,c.name AS client_name,s.name AS site_name,
      coalesce(a.address,s.address) AS address,p.name AS plan_name, srv.service_code, srv.access_method,
      srv.access_router_id,d.name AS access_router_name,srv.status AS service_status, srv.plan_id,
      srv.monthly_price,srv.currency,srv.contracted_on, srv.ip_assignment,srv.pppoe_username,
      host(srv.service_ip) AS service_ip_text,srv.access_mac,srv.technical_notes AS service_notes
    FROM crm.installations i
    JOIN crm.clients c ON (c.company_id,c.id)=(i.company_id,i.client_id)
    JOIN crm.sites s ON (s.company_id,s.id)=(i.company_id,i.site_id)
    LEFT JOIN crm.client_addresses a ON (a.company_id,a.id)=(s.company_id,s.client_address_id)
    JOIN crm.services srv ON (srv.company_id,srv.id)=(i.company_id,i.service_id)
    JOIN crm.service_plans p ON (p.company_id,p.id)=(srv.company_id,srv.plan_id)
    LEFT JOIN crm.devices d ON (d.company_id,d.id)=(srv.company_id,srv.access_router_id)
"""


class Create(schemas.Reason):
    service_id: UUID
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] = "NORMAL"
    observations: schemas.Long | None = None


class Manage(Input):
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] = "NORMAL"
    scheduled_at: AwareDatetime | None = None
    technician_ids: list[UUID] = Field(default_factory=list, max_length=30)
    observations: schemas.Long | None = None
    technical_notes: schemas.Long | None = None


class Transition(schemas.Reason):
    status: Literal["SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
    scheduled_at: AwareDatetime | None = None
    verification: schemas.Long | None = None
    activate_service: bool = True
    monitor_devices: list[UUID] = Field(default_factory=list, max_length=100)


class NewEquipment(Input):
    name: Name
    device_type: schemas.Short | None = None
    type_id: UUID
    manufacturer_id: UUID | None = None
    model_id: UUID | None = None
    device_role: schemas.Role = "ENDPOINT"
    serial_number: schemas.Short | None = None


class Equipment(schemas.Reason):
    device_id: UUID | None = None
    new_device: NewEquipment | None = None
    link_service: bool = False
    ip_mode: Literal["NONE", "INDEPENDENT", "SERVICE"] = "NONE"
    ip_address: schemas.Short | None = None

    @model_validator(mode="after")
    def select_device(self):
        if bool(self.device_id) == bool(self.new_device):
            raise ValueError("Selecciona o registra un equipo.")
        self.ip_address = schemas.address(self.ip_address, ipv4_only=True)
        return self


def check_service(db, company, service):
    site = store.owned(db, "sites", company, service["site_id"])
    client = store.owned(db, "clients", company, service["client_id"])
    if (service["archived_at"] or site["archived_at"] or client["archived_at"] or
            site["client_id"] != client["id"] or not site["active"] or client["status"] != "ACTIVE"):
        raise problem("service_id", "Selecciona un servicio, cliente y sitio vigentes.", 409)


def create_order(db, actor, service_id, *, priority="NORMAL", observations=None, reason=None):
    actor.require("installations.create")
    service = store.owned(db, "services", actor.company, service_id)
    check_service(db, actor.company, service)
    if service["status"] != "PENDING":
        raise problem("service_id", "La orden requiere un servicio pendiente.", 409)
    if row(db, """
        SELECT id FROM crm.installations WHERE company_id=:company AND service_id=:id
        AND status IN ('PENDING','SCHEDULED','IN_PROGRESS')
    """, company=actor.company, id=service_id):
        raise problem("service_id", "El servicio ya tiene una instalación abierta.", 409)
    values = {key: service[key] for key in ("client_id", "site_id")}
    values.update(service_id=service_id, installation_code=store.commercial_code(db, actor.company, "installation"),
                  created_by=actor.user["person_id"], priority=priority, observations=observations)
    order_id = store.insert(db, "installations", actor.company, values)
    store.change_event(db, actor, "installation", order_id, "create", after=values, client=service["client_id"], reason=reason)
    return store.owned(db, "installations", actor.company, order_id)


def open_order(db, actor, order_id):
    order = store.owned(db, "installations", actor.company, order_id)
    if order["archived_at"] or order["status"] in TERMINAL:
        raise HTTPException(409, "La orden finalizada está disponible para consulta.")
    return order


def history(db, actor, order, action, *, new_status=None, detail=None, data=None):
    execute(db, """
        INSERT INTO crm.installation_history(company_id,installation_id,actor_id,action,previous_status,new_status,detail)
        VALUES (:company,:id,:actor,:action,:before,:after,:detail)
    """, company=actor.company, id=order["id"], actor=actor.user["person_id"], action=action,
        before=order["status"], after=new_status or order["status"], detail=detail)
    store.change_event(db, actor, "installation", order["id"], action, before={"status": order["status"]},
                       after=data or {"status": new_status or order["status"]}, client=order["client_id"], reason=detail)


@router.get("")
def listing(request: Request, q: str = Query("", max_length=120), status: str | None = None,
            service_id: UUID | None = None, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    with read(request, "installations.read", ISP) as (db, actor):
        items = rows(db, SELECT + """
            WHERE i.company_id=:company AND (CAST(:service AS uuid) IS NULL OR i.service_id=:service)
              AND CASE WHEN CAST(:status AS text)='ARCHIVED' THEN i.archived_at IS NOT NULL
                ELSE i.archived_at IS NULL AND (:status IS NULL OR i.status=:status) END
              AND strpos(lower(concat_ws(' ',i.installation_code,c.name,s.name)),lower(:q))>0
            ORDER BY i.created_at DESC,i.id OFFSET :offset LIMIT :limit
        """, company=actor.company, service=service_id, status=status, q=q.strip(), offset=offset, limit=limit+1)
        return {"items": items[:limit], "has_more": len(items)>limit}


@router.get("/technicians")
def technicians(request: Request):
    with read(request, "installations.write", ISP) as (db, actor):
        return rows(db, """
            SELECT m.id,u.name FROM core.memberships m JOIN core.users u ON u.id=m.user_id
            WHERE m.company_id=:company AND m.active AND u.active ORDER BY lower(u.name),m.id
        """, company=actor.company)


@router.post("", status_code=201)
def create(request: Request, data: Create):
    with write(request, "installations.create", ISP) as (db, actor):
        return create_order(db, actor, data.service_id, priority=data.priority, observations=data.observations, reason=data.reason)


@router.get("/{order_id}")
def detail(request: Request, order_id: UUID):
    with read(request, "installations.read", ISP) as (db, actor):
        order = row(db, SELECT + " WHERE i.company_id=:company AND i.id=:id", company=actor.company, id=order_id)
        if not order:
            raise HTTPException(404, "Instalación no encontrada.")
        return dict(order, technicians=rows(db, """
            SELECT m.id,u.name FROM crm.installation_technicians t
            JOIN core.memberships m ON (t.company_id,t.membership_id)=(m.company_id,m.id)
            JOIN core.users u ON u.id=m.user_id WHERE t.company_id=:company AND t.installation_id=:id ORDER BY u.name
        """, company=actor.company, id=order_id), devices=rows(db, """
            SELECT d.id,d.name,d.device_code,d.assignment_state,host(d.effective_ip) AS effective_ip
            FROM crm.installation_devices a JOIN crm.device_targets d ON (a.company_id,a.device_id)=(d.company_id,d.id)
            WHERE a.company_id=:company AND a.installation_id=:id ORDER BY d.name
        """, company=actor.company, id=order_id), history=rows(db, """
            SELECT h.occurred_at,h.action,h.previous_status,h.new_status,h.detail,u.name AS actor
            FROM crm.installation_history h JOIN core.memberships m ON (h.company_id,h.actor_id)=(m.company_id,m.id)
            JOIN core.users u ON u.id=m.user_id WHERE h.company_id=:company AND h.installation_id=:id
            ORDER BY h.occurred_at DESC,h.id LIMIT 100
        """, company=actor.company, id=order_id))


@router.put("/{order_id}")
def manage(request: Request, order_id: UUID, data: Manage):
    with write(request, "installations.write", ISP) as (db, actor):
        order = open_order(db, actor, order_id)
        values = data.model_dump(exclude={"technician_ids"})
        if order["status"] == "SCHEDULED" and not data.scheduled_at:
            raise problem("scheduled_at", "Conserva o cambia la fecha programada.")
        if order["status"] == "IN_PROGRESS" and data.scheduled_at != order["scheduled_at"]:
            raise problem("scheduled_at", "Una orden en ejecución conserva su programación.", 409)
        for person in set(data.technician_ids):
            if not row(db, "SELECT id FROM core.memberships WHERE company_id=:company AND id=:id AND active",
                       company=actor.company, id=person):
                raise problem("technician_ids", "El técnico debe ser un miembro activo de esta empresa.")
        execute(db, "DELETE FROM crm.installation_technicians WHERE company_id=:company AND installation_id=:id",
                company=actor.company, id=order_id)
        for person in set(data.technician_ids):
            execute(
                db, "INSERT INTO crm.installation_technicians(company_id,installation_id,membership_id) VALUES (:company,:id,:member)",
                company=actor.company, id=order_id, member=person)
        store.update(db, "installations", actor.company, order_id, values)
        detail = f"Programación de {order['scheduled_at']} a {data.scheduled_at}." if order["scheduled_at"] != data.scheduled_at else None
        history(db, actor, order, "manage", detail=detail, data={**values, "technicians": data.technician_ids})
        return store.owned(db, "installations", actor.company, order_id)


@router.put("/{order_id}/service")
def technical(request: Request, order_id: UUID, data: schemas.ServiceDetails):
    with write(request, "installations.write", ISP) as (db, actor):
        actor.require("services.write")
        order = open_order(db, actor, order_id)
        fields = schemas.Service(**data.model_dump(), client_id=order["client_id"], site_id=order["site_id"])
        return operations.save(db, actor, store.SERVICES, fields, order["service_id"])


@router.post("/{order_id}/devices", status_code=201)
def equipment(request: Request, order_id: UUID, data: Equipment):
    with write(request, "installations.write", ISP) as (db, actor):
        order = open_order(db, actor, order_id)
        actor.require("devices.write")
        device_id = data.device_id
        if data.new_device:
            actor.require("devices.create")
            device_id = operations.save(db, actor, store.DEVICES, schemas.Device(
                **data.new_device.model_dump(), device_category="CUSTOMER_EQUIPMENT"
            ))["id"]
        device = store.owned(db, "devices", actor.company, device_id)
        if device["device_category"] != "CUSTOMER_EQUIPMENT" or device["site_id"] not in (None, order["site_id"]):
            raise problem("device_id", "Selecciona un equipo final disponible o asignado a este sitio.")
        if row(db, """
            SELECT 1 FROM crm.installation_devices a JOIN crm.installations i
            ON (a.company_id,a.installation_id)=(i.company_id,i.id)
            WHERE a.company_id=:company AND a.device_id=:device AND i.id<>:id
            AND i.status NOT IN ('COMPLETED','CANCELLED') LIMIT 1
        """, company=actor.company, device=device_id, id=order_id):
            raise problem("device_id", "El equipo ya está incluido en otra orden abierta.", 409)
        result = operations.assign_device(db, actor, device_id, schemas.Assignment(
            site_id=order["site_id"], client_id=order["client_id"], service_id=order["service_id"] if data.link_service else None,
            assignment_state="INSTALLED" if device["assignment_state"] == "INSTALLED" else "ASSIGNED",
            ip_mode=data.ip_mode, ip_address=data.ip_address, reason=data.reason,
        ))
        execute(db, """
            INSERT INTO crm.installation_devices(company_id,installation_id,device_id)
            VALUES (:company,:id,:device) ON CONFLICT DO NOTHING
        """, company=actor.company, id=order_id, device=device_id)
        history(db, actor, order, "equipment", detail=data.reason, data={"device_id": device_id})
        return result


def complete(db, actor, order, data):
    actor.require("installations.complete")
    if not (data.verification or "").strip():
        raise problem("verification", "Registra el resultado de la verificación, incluso si fue manual.")
    service = store.owned(db, "services", actor.company, order["service_id"])
    check_service(db, actor.company, service)
    if service["status"] not in {"PENDING", "ACTIVE"}:
        raise HTTPException(409, "Se requiere un servicio pendiente o activo para completar la orden.")
    devices = rows(db, """
        SELECT d.* FROM crm.installation_devices a JOIN crm.devices d ON (a.company_id,a.device_id)=(d.company_id,d.id)
        WHERE a.company_id=:company AND a.installation_id=:id ORDER BY d.id
    """, company=actor.company, id=order["id"])
    if not set(data.monitor_devices) <= {device["id"] for device in devices}:
        raise problem("monitor_devices", "Selecciona equipos de esta orden.")
    for device in devices:
        actor.require("devices.write")
        if device["site_id"] != order["site_id"] or device["service_id"] not in (None, order["service_id"]):
            raise HTTPException(409, "Un equipo de la orden cambió de ubicación o servicio.")
        operations.assign_device(db, actor, device["id"], schemas.Assignment(
            site_id=device["site_id"], service_id=device["service_id"], assignment_state="INSTALLED",
            ip_mode=device["ip_mode"], ip_address=str(device["ip_address"]) if device["ip_address"] else None, reason=data.reason,
        ))
        if device["id"] in data.monitor_devices:
            actor.require("icmp.write")
            profile = operations.profile(db, actor.company, device["id"])
            profile.pop("configured")
            if not device["monitoring_requested"]:
                profile["interval_seconds"] = max(profile["interval_seconds"], actor.plan["min_poll_interval_seconds"] or 5)
            operations.save_profile(db, actor, device["id"], schemas.IcmpProfile(**(profile | {"requested": True})))
    if data.activate_service and service["status"] == "PENDING":
        actor.require("services.status")
        operations.service_status(db, actor, service["id"], schemas.ServiceState(status="ACTIVE", reason=data.reason))


@router.post("/{order_id}/status")
def transition(request: Request, order_id: UUID, data: Transition):
    permission = "installations.complete" if data.status == "COMPLETED" else "installations.write"
    with write(request, permission, ISP) as (db, actor):
        order = open_order(db, actor, order_id)
        if data.status not in TRANSITIONS.get(order["status"], set()):
            raise problem("status", "La transición de la instalación no está permitida.", 409)
        values = {"status": data.status}
        if data.status == "SCHEDULED":
            values["scheduled_at"] = data.scheduled_at or order["scheduled_at"]
            if not values["scheduled_at"]:
                raise problem("scheduled_at", "Indica la fecha programada.")
        elif data.status == "COMPLETED":
            complete(db, actor, order, data)
            values.update(completed_at=datetime.now(UTC), verification=data.verification)
        store.update(db, "installations", actor.company, order_id, values)
        scheduling = f" Fecha programada anterior: {order['scheduled_at']}. Nueva: {values['scheduled_at']}." if "scheduled_at" in values else ""
        history(db, actor, order, "status", new_status=data.status, detail=data.reason + scheduling, data=values)
        return store.owned(db, "installations", actor.company, order_id)


@router.post("/{order_id}/archive")
def archive(request: Request, order_id: UUID, data: schemas.Reason):
    with write(request, "installations.archive", ISP) as (db, actor):
        order = store.owned(db, "installations", actor.company, order_id)
        if order["status"] not in TERMINAL:
            raise HTTPException(409, "Completa o cancela la orden antes de archivarla.")
        if not order["archived_at"]:
            store.update(db, "installations", actor.company, order_id, {"archived_at": datetime.now(UTC)})
            history(db, actor, order, "archive", detail=data.reason)
        return store.owned(db, "installations", actor.company, order_id)


@router.delete("/{order_id}", status_code=204)
def delete(request: Request, order_id: UUID, data: schemas.Delete):
    with write(request, "installations.delete", ISP) as (db, actor):
        order = open_order(db, actor, order_id)
        if order["status"] != "PENDING":
            raise HTTPException(409, "Solo se puede eliminar un borrador pendiente.")
        lifecycle.delete(db, actor, ORDERS, order_id, data)
