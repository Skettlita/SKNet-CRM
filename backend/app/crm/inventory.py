from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy.exc import IntegrityError

from app.auth.schemas import Input
from app.auth.store import ISP, audit, execute, row, rows
from app.crm import operations, schemas, store
from app.crm.classification import DeviceCategory
from app.platform.routes import read, write
from app.validation import problem


router = APIRouter(prefix=ISP.path + "/inventory", tags=["Inventario básico"])
Section = Literal["types", "manufacturers", "models"]
TABLES = {"types": "device_types", "manufacturers": "manufacturers", "models": "device_models"}
MODEL_SELECT = """
    SELECT m.*,t.name AS type_name,f.name AS manufacturer_name,
           m.active AND t.active AND f.active AS eligible
    FROM inventory.device_models m
    JOIN inventory.device_types t ON (t.company_id,t.id)=(m.company_id,m.type_id)
    JOIN inventory.manufacturers f ON (f.company_id,f.id)=(m.company_id,m.manufacturer_id)
"""


class CatalogEntry(Input):
    name: schemas.Short
    type_id: UUID | None = None
    manufacturer_id: UUID | None = None
    active: bool = True


class Batch(Input):
    model_id: UUID
    device_category: DeviceCategory
    quantity: int = Field(ge=1, le=200)
    ownership: Literal["ISP", "CUSTOMER", "THIRD_PARTY", "UNKNOWN"] = "ISP"
    device_role: schemas.Role | None = None
    description: schemas.Long | None = None


class ModelAssignment(schemas.Assignment):
    model_id: UUID
    device_category: DeviceCategory


def catalog_row(db, company, section, identifier):
    if section == "models":
        return row(db, MODEL_SELECT+" WHERE m.company_id=:company AND m.id=:id", company=company, id=identifier)
    return row(db, f"SELECT * FROM inventory.{TABLES[section]} WHERE company_id=:company AND id=:id",
               company=company, id=identifier)


def require_catalog(db, company, section, identifier, field, *, active=True):
    result = catalog_row(db, company, section, identifier)
    if not result or active and not result.get("eligible", result["active"]):
        raise problem(field, "Selecciona un registro de catálogo vigente de tu empresa.")
    return result


def device_labels(db, company, fields, values, previous):
    model_id, manufacturer_id, type_id = fields.model_id, fields.manufacturer_id, fields.type_id
    changed = bool({"type_id", "manufacturer_id", "model_id"} & fields.model_fields_set)
    if previous and not changed:
        values.update({key: previous[key] for key in ("type_id","manufacturer_id","model_id","device_type","brand","model")})
        return
    if model_id:
        model = require_catalog(db, company, "models", model_id, "model_id",
                                active=not previous or previous["model_id"] != model_id)
        if type_id and type_id != model["type_id"] or manufacturer_id and manufacturer_id != model["manufacturer_id"]:
            raise problem("model_id", "El modelo no corresponde al tipo o fabricante seleccionado.")
        values.update(type_id=model["type_id"], manufacturer_id=model["manufacturer_id"], model_id=model_id,
                      device_type=model["type_name"], brand=model["manufacturer_name"], model=model["name"])
        return
    if not type_id:
        raise problem("type_id", "Selecciona un tipo del catálogo de tu empresa.")
    kind = require_catalog(db, company, "types", type_id, "type_id", active=not previous or previous["type_id"] != type_id)
    manufacturer = require_catalog(db, company, "manufacturers", manufacturer_id, "manufacturer_id",
                                    active=not previous or previous["manufacturer_id"] != manufacturer_id) if manufacturer_id else None
    values.update(type_id=type_id, manufacturer_id=manufacturer_id, model_id=None, device_type=kind["name"],
                  brand=manufacturer["name"] if manufacturer else None,
                  model=previous["model"] if previous and previous["model_id"] is None and previous["type_id"] == type_id
                    and previous["manufacturer_id"] == manufacturer_id else None)


def save_catalog(db, actor, section, data, identifier=None):
    previous = catalog_row(db, actor.company, section, identifier) if identifier else None
    if identifier and not previous:
        raise HTTPException(404, "Registro de catálogo no encontrado.")
    values = data.model_dump() if section == "models" else data.model_dump(include={"name","active"})
    if section == "models":
        require_catalog(db, actor.company, "types", data.type_id, "type_id", active=data.active)
        require_catalog(db, actor.company, "manufacturers", data.manufacturer_id, "manufacturer_id", active=data.active)
        if previous and (data.type_id != previous["type_id"] or data.manufacturer_id != previous["manufacturer_id"]):
            if row(db, "SELECT id FROM crm.devices WHERE company_id=:company AND model_id=:id LIMIT 1", company=actor.company, id=identifier):
                raise problem("model_id", "Hay unidades de este modelo. Crea otro modelo para cambiar el fabricante o tipo.", 409)
    table = TABLES[section]
    try:
        with db.begin_nested():
            if identifier:
                execute(db, f"UPDATE inventory.{table} SET "+", ".join(f"{key}=:{key}" for key in values)
                        +" WHERE company_id=:company AND id=:id", company=actor.company, id=identifier, **values)
            else:
                names = ",".join(values)
                params = ",".join(f":{key}" for key in values)
                identifier = execute(db, f"""
                    INSERT INTO inventory.{table}(company_id,{names}) VALUES (:company,{params}) RETURNING id
                """, company=actor.company, **values).scalar_one()
    except IntegrityError:
        raise problem("name", "Ya existe un registro de catálogo con esos datos.", 409) from None
    audit(db, "inventory.catalog.update" if previous else "inventory.catalog.create", table, identifier,
          company=actor.company, actor=actor.id, after=values)
    return catalog_row(db, actor.company, section, identifier)


@router.get("/catalog/{section}")
def catalogs(request: Request, section: Section, only_active: bool = False, q: str = Query("", max_length=120),
             offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    with read(request, "inventory.read", ISP) as (db, actor):
        select = MODEL_SELECT if section == "models" else f"SELECT m.* FROM inventory.{TABLES[section]} m"
        enabled = "m.active AND t.active AND f.active" if section == "models" else "m.active"
        matches = "concat_ws(' ',m.name,t.name,f.name)" if section == "models" else "m.name"
        entries = rows(db, select+f"""
            WHERE m.company_id=:company AND (NOT :active OR ({enabled}))
              AND strpos(lower({matches}),lower(:q))>0
            ORDER BY lower(m.name),m.id LIMIT :limit OFFSET :offset
        """, company=actor.company, active=only_active, q=q.strip(), limit=limit+1, offset=offset)
        return {"items": entries[:limit], "has_more": len(entries)>limit}


@router.post("/catalog/{section}", status_code=201)
def create_catalog(request: Request, section: Section, data: CatalogEntry):
    with write(request, "inventory.write", ISP) as (db, actor):
        return save_catalog(db, actor, section, data)


@router.put("/catalog/{section}/{identifier}")
def edit_catalog(request: Request, section: Section, identifier: UUID, data: CatalogEntry):
    with write(request, "inventory.write", ISP) as (db, actor):
        return save_catalog(db, actor, section, data, identifier)


@router.delete("/catalog/{section}/{identifier}", status_code=204)
def delete_catalog(request: Request, section: Section, identifier: UUID):
    with write(request, "inventory.write", ISP) as (db, actor):
        if not catalog_row(db, actor.company, section, identifier):
            raise HTTPException(404, "Registro de catálogo no encontrado.")
        try:
            with db.begin_nested():
                execute(db, f"DELETE FROM inventory.{TABLES[section]} WHERE company_id=:company AND id=:id",
                        company=actor.company, id=identifier)
        except IntegrityError:
            raise HTTPException(409, "El catálogo tiene modelos o unidades asociados. Puedes desactivarlo.") from None
        audit(db, "inventory.catalog.delete", TABLES[section], identifier, actor=actor.id, company=actor.company)


@router.get("/stock")
def stock(request: Request, available: bool = False, category: DeviceCategory | None = None,
          q: str = Query("", max_length=120), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    with read(request, "inventory.read", ISP) as (db, actor):
        entries = rows(db, """
            WITH grouped AS (
              SELECT d.model_id,d.type_id,d.manufacturer_id,
                coalesce(t.name,d.device_type) AS type_name,coalesce(f.name,d.brand) AS manufacturer_name,
                coalesce(m.name,d.model) AS model_name,
                count(*) AS total,
                count(*) FILTER(WHERE d.assignment_state='AVAILABLE' AND d.administrative_active AND d.archived_at IS NULL
                  AND d.retired_at IS NULL AND d.site_id IS NULL AND d.service_id IS NULL) AS available,
                count(*) FILTER(WHERE d.assignment_state='ASSIGNED') AS assigned,
                count(*) FILTER(WHERE d.assignment_state='INSTALLED') AS installed,
                count(*) FILTER(WHERE d.assignment_state='MAINTENANCE') AS maintenance,
                count(*) FILTER(WHERE d.assignment_state='RETIRED') AS retired
              FROM crm.devices d JOIN inventory.device_types t ON (t.company_id,t.id)=(d.company_id,d.type_id)
              LEFT JOIN inventory.manufacturers f ON (f.company_id,f.id)=(d.company_id,d.manufacturer_id)
              LEFT JOIN inventory.device_models m ON (m.company_id,m.id)=(d.company_id,d.model_id)
              WHERE d.company_id=:company AND (CAST(:category AS text) IS NULL OR d.device_category=:category)
                AND (NOT :available OR (m.active AND t.active AND f.active))
              GROUP BY 1,2,3,4,5,6
            )
            SELECT *,coalesce(model_id::text,type_id::text || ':' || coalesce(manufacturer_id::text,'-') || ':' ||
                 coalesce(model_name,'')) AS id FROM grouped
            WHERE (NOT :available OR available>0) AND strpos(lower(concat_ws(' ',type_name,manufacturer_name,model_name)),lower(:q))>0
            ORDER BY lower(manufacturer_name) NULLS LAST,lower(model_name) NULLS LAST,id LIMIT :limit OFFSET :offset
        """, company=actor.company, available=available, category=category, q=q.strip(), limit=limit+1, offset=offset)
        return {"items": entries[:limit], "has_more": len(entries)>limit}


@router.get("/stock/units")
def stock_units(request: Request, model_id: UUID | None = None, type_id: UUID | None = None,
                manufacturer_id: UUID | None = None, old_model: str | None = Query(None, max_length=400),
                offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    with read(request, "inventory.read", ISP) as (db, actor):
        data = rows(db, """
            SELECT id,device_code,name,device_category,assignment_state,serial_number,mac_address,ownership
            FROM crm.devices WHERE company_id=:company AND (
                (CAST(:model AS uuid) IS NOT NULL AND model_id=:model)
                OR (CAST(:model AS uuid) IS NULL AND model_id IS NULL AND type_id=:type
                    AND manufacturer_id IS NOT DISTINCT FROM CAST(:manufacturer AS uuid)
                    AND coalesce(model,'')=coalesce(:old,''))
            ) ORDER BY device_code,id LIMIT :limit OFFSET :offset
        """, company=actor.company, model=model_id, type=type_id, manufacturer=manufacturer_id, old=old_model,
            limit=limit+1, offset=offset)
        return {"items": data[:limit], "has_more": len(data)>limit}


@router.post("/stock/batches", status_code=201)
def create_batch(request: Request, data: Batch):
    with write(request, "inventory.write", ISP) as (db, actor):
        model = require_catalog(db, actor.company, "models", data.model_id, "model_id")
        numbers = store.commercial_numbers(db, actor.company, "device", data.quantity)
        units = rows(db, """
            INSERT INTO crm.devices(company_id,name,device_code,device_type,brand,model,device_category,ownership,device_role,
                type_id,manufacturer_id,model_id,description)
            SELECT :company,:name,'DSP-'||lpad(n::text,greatest(6,length(n::text)),'0'),:type_name,:manufacturer_name,
                :model_name,:category,:ownership,:role,:type,:manufacturer,:model,:description
            FROM generate_series(CAST(:start AS bigint),CAST(:end AS bigint)) n
            RETURNING id,device_code
        """, company=actor.company, name=f"{model['manufacturer_name']} {model['name']}"[:120],
            type_name=model["type_name"], manufacturer_name=model["manufacturer_name"], model_name=model["name"],
            category=data.device_category, ownership=data.ownership, role=data.device_role or (
                "ENDPOINT" if data.device_category=="CUSTOMER_EQUIPMENT" else "NODE"),
            type=model["type_id"], manufacturer=model["manufacturer_id"], model=data.model_id,
            description=data.description, start=numbers.start, end=numbers.stop-1)
        audit(db, "inventory.batch.create", "device_model", data.model_id, actor=actor.id, company=actor.company,
              after={"quantity": data.quantity, "units": [item["device_code"] for item in units]})
        return {"items": units}


def take_available(db, actor, selection, *, category):
    actor.require("devices.write")
    actor.require("inventory.read")
    if selection.model_id:
        require_catalog(db, actor.company, "models", selection.model_id, "model_id")
    device = row(db, """
        SELECT id FROM crm.devices WHERE company_id=:company AND device_category=:category AND assignment_state='AVAILABLE'
          AND archived_at IS NULL AND retired_at IS NULL AND administrative_active AND site_id IS NULL AND service_id IS NULL
          AND (CAST(:model AS uuid) IS NULL OR model_id=:model)
          AND (CAST(:device AS uuid) IS NULL OR id=:device)
        ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED
    """, company=actor.company, category=category, model=selection.model_id, device=selection.device_id)
    if not device:
        field = "model_id" if selection.model_id else "device_id"
        raise problem(field, "No quedan unidades disponibles para esta selección.", 409)
    return device["id"]


@router.post("/stock/assign")
def assign_from_stock(request: Request, data: ModelAssignment):
    with write(request, "devices.write", ISP) as (db, actor):
        if not data.site_id:
            raise problem("site_id", "Selecciona el sitio al que se asignará el equipo.")
        unit = take_available(db, actor, schemas.EquipmentSelection(model_id=data.model_id), category=data.device_category)
        return operations.assign_device(db, actor, unit, schemas.Assignment(**data.model_dump(
            exclude={"model_id","device_category"}
        )))
