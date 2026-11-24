from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.auth.store import execute, rows
from app.crm import store


DEPENDENCIES = {
    "clients": ("clientes", "Los datos asociados al cliente deben conservarse."),
    "services": ("servicios", "El servicio tiene historial operativo o registros asociados."),
    "service_plans": ("planes", "El plan tiene servicios u otros registros asociados."),
    "sites": ("sitios", "El sitio tiene equipos, servicios u otros registros asociados."),
    "devices": ("equipos", "El equipo tiene servicios, asignaciones o historial técnico."),
    "installations": ("instalaciones", "La orden tiene técnicos, equipos o historial de ejecución."),
}
LABELS = {
    "client_contacts": "contactos", "client_addresses": "direcciones", "client_notes": "notas",
    "sites": "sitios", "services": "servicios", "devices": "equipos", "contracts": "contratos",
    "charges": "deudas", "payments": "pagos", "billing_profiles": "perfiles de facturación",
    "service_status_history": "historial de estados", "icmp_profiles": "perfiles ICMP",
    "icmp_checks": "mediciones ICMP", "incidents": "incidentes", "installations": "instalaciones",
    "installation_history": "historial de instalaciones", "installation_devices": "equipos de instalación",
    "installation_technicians": "técnicos de instalación", "device_assignments": "historial de asignaciones",
}
INITIAL_SERVICE_HISTORY = "previous_status IS NULL AND new_status IN ('PENDING','ACTIVE')"


def archive(db, actor, resource, record_id, data):
    previous = store.owned(db, resource.table, actor.company, record_id)
    if previous["archived_at"]:
        return store.details(db, resource, actor.company, record_id)
    changed = {"archived_at": datetime.now(UTC)}
    if resource is store.DEVICES:
        from app.crm.operations import assignment_history, close_monitoring_incident

        changed.update(retired_at=previous["retired_at"] or changed["archived_at"], monitoring_enabled=False,
                       assignment_state="RETIRED", administrative_active=False,
                       config_revision=previous["config_revision"] + 1)
        assignment_history(db, actor, record_id, previous, {**previous, **changed}, data.reason)
        close_monitoring_incident(db, actor.company, record_id, "RETIRED")
    store.update(db, resource.table, actor.company, record_id, changed)
    if resource is store.SERVICES:
        from app.crm.operations import revise_service_targets

        revise_service_targets(db, actor.company, record_id, None)
    store.change_event(db, actor, resource.entity, record_id, "archive", after=changed,
                       client=previous.get("client_id"), reason=data.reason)
    return store.details(db, resource, actor.company, record_id)


def references(db, table, record_id):
    quote = db.bind.dialect.identifier_preparer.quote_identifier
    keys = rows(db, """
        SELECT DISTINCT s.nspname AS schema,c.relname AS tab,source.attname AS col
        FROM pg_constraint f
        JOIN pg_class c ON c.oid=f.conrelid JOIN pg_namespace s ON s.oid=c.relnamespace
        CROSS JOIN LATERAL unnest(f.conkey,f.confkey) AS pair(src,dst)
        JOIN pg_attribute source ON source.attrelid=f.conrelid AND source.attnum=pair.src
        JOIN pg_attribute target ON target.attrelid=f.confrelid AND target.attnum=pair.dst
        WHERE f.contype='f' AND f.confrelid=to_regclass(:target) AND target.attname='id'
    """, target="crm." + table)
    dependencies = set()
    for key in keys:
        qualified = quote(key["schema"]) + "." + quote(key["tab"])
        clause = ""
        if table == "services" and key["tab"] == "service_status_history":
            clause = f"AND NOT ({INITIAL_SERVICE_HISTORY})"
        if execute(db, f"SELECT EXISTS(SELECT 1 FROM {qualified} WHERE {quote(key['col'])}=:id {clause})",
                   id=record_id).scalar_one():
            dependencies.add(LABELS.get(key["tab"], key["tab"].replace("_", " ")))
    return sorted(dependencies)


def delete(db, actor, resource, record_id, data):
    previous = store.owned(db, resource.table, actor.company, record_id)
    blockers = references(db, resource.table, record_id)
    if blockers:
        raise HTTPException(409, detail={"message": "El registro tiene dependencias protegidas. Puedes archivarlo.",
                                        "dependencies": blockers})
    if resource is store.SERVICES and previous["status"] not in {"PENDING", "ACTIVE"}:
        raise HTTPException(409, DEPENDENCIES["services"][1])
    if resource is store.DEVICES and (previous["installed_at"] or previous["asset_id"] or previous["site_id"]):
        raise HTTPException(409, DEPENDENCIES["devices"][1])
    try:
        with db.begin_nested():
            if resource is store.SERVICES:
                execute(db, f"""
                    DELETE FROM crm.service_status_history WHERE company_id=:company AND service_id=:id
                    AND {INITIAL_SERVICE_HISTORY}
                """, company=actor.company, id=record_id)
            execute(db, f"DELETE FROM crm.{resource.table} WHERE company_id=:company AND id=:id",
                    company=actor.company, id=record_id)
    except IntegrityError:
        raise HTTPException(409, "El registro tiene relaciones protegidas. Puedes archivarlo.") from None
    code = previous.get(resource.entity + "_code")
    store.change_event(db, actor, resource.entity, record_id, "delete", before={"code": code},
                       client=previous.get("client_id"), reason=data.reason)
