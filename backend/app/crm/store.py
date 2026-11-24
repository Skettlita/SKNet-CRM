from dataclasses import dataclass

from fastapi import HTTPException

from app.auth.store import audit, execute, row, rows


@dataclass(frozen=True)
class Resource:
    table: str
    entity: str
    order: str
    search: str
    status: str
    extra: str = ""
    joins: str = ""
    client: str = "NULL::uuid"
    site: str = "NULL::uuid"


CLIENTS = Resource("clients", "client", "t.name", "concat_ws(' ',t.name,t.client_code,t.document_number,t.email,t.phone)",
                   "t.status", client="t.id")
PLANS = Resource("service_plans", "internet_plan", "t.name", "t.name", "CASE WHEN t.active THEN 'ACTIVE' ELSE 'INACTIVE' END")
SITES = Resource("sites", "site", "t.name", "concat_ws(' ',t.name,t.city,t.address)",
                 "CASE WHEN t.active THEN 'ACTIVE' ELSE 'INACTIVE' END", ", c.name AS client_name",
                 "LEFT JOIN crm.clients c ON c.company_id=t.company_id AND c.id=t.client_id", "t.client_id", "t.id")
SERVICES = Resource("services", "service", "c.name", "concat_ws(' ',c.name,s.name,p.name,t.pppoe_username,host(t.service_ip))",
                    "t.status", """,
                    c.name AS client_name,s.name AS site_name,p.name AS plan_name,
                    router.name AS access_router_name,host(t.service_ip) AS service_ip_text
                    """, """
                    JOIN crm.clients c ON c.company_id=t.company_id AND c.id=t.client_id
                    JOIN crm.sites s ON s.company_id=t.company_id AND s.id=t.site_id
                    JOIN crm.service_plans p ON p.company_id=t.company_id AND p.id=t.plan_id
                    LEFT JOIN crm.devices router ON router.company_id=t.company_id AND router.id=t.access_router_id
                    """, "t.client_id", "t.site_id")
DEVICES = Resource("devices", "device", "t.name", "concat_ws(' ',t.name,t.brand,t.model,host(t.ip_address),s.name)",
                   "CASE WHEN t.administrative_active AND t.retired_at IS NULL THEN 'ACTIVE' ELSE 'INACTIVE' END",
                   """, s.name AS site_name,s.client_id,c.name AS client_name,p.name AS service_plan_name,
                   host(t.ip_address) AS ip_address_text,
                   CASE WHEN NOT t.administrative_active OR t.retired_at IS NOT NULL
                      OR NOT (t.monitoring_requested OR t.monitoring_enabled) THEN 'DISABLED'
                      ELSE 'UNKNOWN' END AS monitoring_state
                   """, """
                   JOIN crm.sites s ON s.company_id=t.company_id AND s.id=t.site_id
                   LEFT JOIN crm.clients c ON c.company_id=s.company_id AND c.id=s.client_id
                   LEFT JOIN crm.services srv ON srv.company_id=t.company_id AND srv.id=t.service_id
                   LEFT JOIN crm.service_plans p ON p.company_id=srv.company_id AND p.id=srv.plan_id
                   """, "s.client_id", "t.site_id")

CONTACTS = "client_contacts"
ADDRESSES = "client_addresses"
NOTES = "client_notes"


def owned(db, table, company, record_id):
    value = row(db, f"SELECT * FROM crm.{table} WHERE company_id=:company AND id=:id", company=company, id=record_id)
    if value is None:
        raise HTTPException(404, "Registro no encontrado en tu empresa.")
    return value


def details(db, resource, company, record_id):
    value = row(db, f"""
        SELECT t.*{resource.extra} FROM crm.{resource.table} t {resource.joins}
        WHERE t.company_id=:company AND t.id=:id
    """, company=company, id=record_id)
    if not value:
        raise HTTPException(404, "Registro no encontrado en tu empresa.")
    return value


def listing(db, resource, company, *, q, status, sort, direction, offset, limit,
            client=None, site=None, category=None):
    ordering = {"name": f"lower({resource.order})", "created": "t.created_at", "status": resource.status}[sort]
    sort_dir = "DESC" if direction == "desc" else "ASC"
    kind_column = {
        "clients": "t.client_type", "sites": "t.site_type", "devices": "t.device_role",
        "services": "t.access_method", "service_plans": "t.service_type",
    }[resource.table]
    values = rows(db, f"""
        SELECT t.*{resource.extra} FROM crm.{resource.table} t {resource.joins}
        WHERE t.company_id=:company AND strpos(lower({resource.search}),lower(:q))>0
          AND (CAST(:status AS text) IS NULL OR {resource.status}=:status)
          AND (CAST(:category AS text) IS NULL OR {kind_column}=:category)
          AND (CAST(:client AS uuid) IS NULL OR {resource.client}=:client)
          AND (CAST(:site AS uuid) IS NULL OR {resource.site}=:site)
        ORDER BY {ordering} {sort_dir},t.id OFFSET :offset LIMIT :limit
    """, company=company, q=q.strip(), status=status, offset=offset, limit=limit + 1,
        client=client, site=site, category=category)
    return {"items": values[:limit], "has_more": len(values) > limit}


def insert(db, table, company, data):
    columns = ", ".join(data)
    values = ", ".join(f":{key}" for key in data)
    return execute(db, f"""
        INSERT INTO crm.{table}(company_id,{columns}) VALUES (:company,{values}) RETURNING id
    """, company=company, **data).scalar_one()


def update(db, table, company, record_id, data):
    changes = ", ".join(f"{key}=:{key}" for key in data)
    execute(db, f"UPDATE crm.{table} SET {changes} WHERE company_id=:company AND id=:id",
            company=company, id=record_id, **data)


def change_event(db, actor, entity, record_id, action, before=None, after=None, *, client=None, reason=None):
    def clean(values):
        if values is None:
            return None
        private_text = {"observations", "description", "technical_notes", "body", "pppoe_username"}
        result = {key: val for key, val in values.items() if key not in private_text}
        if client is not None:
            result.setdefault("client_id", client)
        return result

    audit(db, f"crm.{entity}.{action}", entity, record_id, actor=actor.id, company=actor.company,
          before=clean(before), after=clean(after), reason=reason)


def enforce_limit(db, actor, key, table, clause=""):
    maximum = actor.plan[key]
    if maximum is None:
        return
    count = execute(db, f"SELECT count(*) FROM crm.{table} WHERE company_id=:company {clause}",
                    company=actor.company).scalar_one()
    if count >= maximum:
        names = {"max_clients": "clientes registrados", "max_devices": "dispositivos reservados para monitoreo"}
        raise HTTPException(409, f"El plan alcanzó su límite de {names[key]}.")


def history(db, company, resource, record_id, offset, limit):
    # Client activity also captures operations on records tied to that client.
    related = """
      OR (e.before_data->>'client_id'=CAST(:id AS text) OR e.after_data->>'client_id'=CAST(:id AS text))
    """ if resource is CLIENTS else ""
    data = rows(db, f"""
        SELECT e.id,e.entity_type,e.entity_id,e.action,e.occurred_at,u.name AS actor
        FROM audit.events e LEFT JOIN core.users u ON u.id=e.actor_user_id
        WHERE e.company_id=:company AND starts_with(e.action,'crm.')
          AND ((e.entity_type=:entity AND e.entity_id=:id) {related})
        ORDER BY e.occurred_at DESC,e.id OFFSET :offset LIMIT :limit
    """, company=company, entity=resource.entity, id=record_id, offset=offset, limit=limit + 1)
    return {"items": data[:limit], "has_more": len(data) > limit}
