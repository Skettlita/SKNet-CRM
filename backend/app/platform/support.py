from fastapi import HTTPException

from app.auth.store import SAAS, audit, execute, person_permissions, row, rows


OPEN_STATES = ("OPEN", "ASSIGNED", "IN_PROGRESS")
TRANSITIONS = {
    "OPEN": {"ASSIGNED", "IN_PROGRESS", "CANCELLED"},
    "ASSIGNED": {"OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"},
    "IN_PROGRESS": {"OPEN", "ASSIGNED", "RESOLVED", "CANCELLED"},
    "RESOLVED": {"OPEN", "CLOSED"},
    "CLOSED": {"OPEN"},
    "CANCELLED": set(),
}
SUMMARY = """
    t.id, t.company_id, c.name AS company_name, t.subject, t.priority, t.status, t.origin,
    t.opened_at, t.closed_at
"""
JOIN = "FROM platform.support_tickets t JOIN core.companies c ON c.id=t.company_id"


def list_tickets(db, company, priority, status, search, offset, limit, *, automatic=False):
    return rows(db, f"""
        SELECT {SUMMARY} {JOIN}
        WHERE (CAST(:company AS uuid) IS NULL OR t.company_id=:company)
           AND (CAST(:priority AS text) IS NULL OR t.priority=:priority)
           AND (CAST(:status AS text) IS NULL OR t.status=:status)
           AND (NOT :automatic OR t.origin='SYSTEM')
           AND strpos(lower(t.subject),lower(:search)) > 0
        ORDER BY t.opened_at DESC,t.id OFFSET :offset LIMIT :limit
    """, company=company, priority=priority, status=status, search=search, offset=offset, limit=limit,
        automatic=automatic)


def ticket(db, actor, ticket_id, *, lock=False):
    params = " AND t.company_id = :company" if actor.realm.isp else ""
    locking = " FOR UPDATE OF t" if lock else ""
    entry = row(db, f"""
        SELECT {SUMMARY}, t.description,t.assigned_staff_id,t.closure_reason {JOIN}
        WHERE t.id=:id {params}{locking}
    """, id=ticket_id, company=actor.company)
    if entry is None:
        raise HTTPException(404, "Solicitud de soporte no encontrada.")
    return entry


def detail(db, actor, ticket_id):
    target = ticket(db, actor, ticket_id)
    company = target["company_id"]
    comments = rows(db, """
        SELECT cm.id,cm.body,cm.internal,cm.created_at,
               CASE WHEN :isp AND u.account_scope='SAAS' THEN 'SKNet' ELSE u.name END AS author
        FROM platform.support_ticket_comments cm JOIN core.users u ON u.id=cm.author_user_id
        WHERE cm.company_id=:company AND cm.ticket_id=:id AND (NOT :isp OR NOT cm.internal)
        ORDER BY cm.created_at,cm.id
    """, company=company, id=ticket_id, isp=actor.realm.isp)
    history = rows(db, """
        SELECT h.id,h.previous_status,h.new_status,h.changed_at,
               CASE WHEN :isp THEN NULL ELSE h.reason END AS reason,
               CASE WHEN h.actor_type='SYSTEM' THEN 'Sistema'
                    WHEN :isp AND u.account_scope='SAAS' THEN 'SKNet' ELSE u.name END AS actor
        FROM platform.support_ticket_history h LEFT JOIN core.users u ON u.id=h.changed_by
        WHERE h.company_id=:company AND h.ticket_id=:id
        ORDER BY h.changed_at,h.id
    """, company=company, id=ticket_id, isp=actor.realm.isp)
    info = dict(target)
    if actor.realm.isp:
        info.pop("assigned_staff_id")
        info.pop("closure_reason")
    return {**info, "comments": comments, "history": history}


def history_entry(db, ticket_id, company, actor, previous, status, reason=None):
    execute(db, """
        INSERT INTO platform.support_ticket_history(company_id,ticket_id,changed_by,previous_status,new_status,reason)
        VALUES (:company,:ticket,:actor,:old,:new,:reason)
    """, company=company, ticket=ticket_id, actor=actor, old=previous, new=status, reason=reason)


def create(db, actor, data):
    ticket_id = execute(db, """
        INSERT INTO platform.support_tickets(company_id,requested_by,subject,description,priority)
        VALUES (:company,:member,:subject,:description,:priority) RETURNING id
    """, company=actor.company, member=actor.user["person_id"], **data.model_dump()).scalar_one()
    history_entry(db, ticket_id, actor.company, actor.id, None, "OPEN")
    audit(db, "support.create", "support_ticket", ticket_id, company=actor.company, actor=actor.id,
          after={"status": "OPEN", "priority": data.priority})
    return {"id": ticket_id}


def staff_choices(db):
    return rows(db, """
        SELECT s.id,u.name FROM platform.staff s JOIN core.users u ON u.id=s.user_id
        WHERE s.active AND u.active AND EXISTS(
            SELECT 1 FROM platform.staff_roles a JOIN platform.role_permissions rp ON rp.role_id=a.role_id
            JOIN platform.permissions p ON p.id=rp.permission_id WHERE a.staff_id=s.id AND p.code='support.write'
        ) ORDER BY lower(u.name),s.id
    """)


def update(db, actor, ticket_id, data):
    entry = ticket(db, actor, ticket_id, lock=True)
    status = data.status
    if status != entry["status"] and status not in TRANSITIONS[entry["status"]]:
        raise HTTPException(409, "La transición de estado no está permitida.")
    if status in {"ASSIGNED", "IN_PROGRESS"} and data.assigned_staff_id is None:
        raise HTTPException(422, "Selecciona un responsable para este estado.")
    if data.assigned_staff_id and data.assigned_staff_id != entry["assigned_staff_id"]:
        assignee = row(db, """
            SELECT s.id FROM platform.staff s JOIN core.users u ON u.id=s.user_id
            WHERE s.id=:id AND s.active AND u.active
        """, id=data.assigned_staff_id)
        if not assignee or "support.write" not in person_permissions(db, SAAS, assignee["id"]):
            raise HTTPException(422, "Selecciona un responsable habilitado para gestionar soporte.")
    after = data.model_dump(exclude={"reason"})
    before = {key: entry[key] for key in after}
    if before != after:
        execute(db, """
            UPDATE platform.support_tickets SET priority=:priority, status=:status, assigned_staff_id=:assigned_staff_id,
              closure_reason=CASE WHEN :status='CANCELLED' THEN :reason ELSE NULL END,
              closed_at=CASE WHEN :status IN ('CLOSED','CANCELLED') THEN COALESCE(closed_at,now()) ELSE NULL END
            WHERE id=:id AND company_id=:company
        """, id=ticket_id, company=entry["company_id"], reason=data.reason, **after)
        change = "Asignación o prioridad actualizada." if entry["status"] == status else data.reason
        history_entry(db, ticket_id, entry["company_id"], actor.id, entry["status"], status, change)
        audit(db, "support.update", "support_ticket", ticket_id, company=entry["company_id"], actor=actor.id,
              before=before, after=after)
    return {"id": ticket_id}


def reply(db, actor, ticket_id, data):
    target = ticket(db, actor, ticket_id, lock=True)
    if target["status"] in {"CLOSED", "CANCELLED"}:
        raise HTTPException(409, "El ticket está cerrado para respuestas.")
    if actor.realm.isp and data.internal:
        raise HTTPException(403, "Las notas internas son exclusivas de SKNet.")
    comment = execute(db, """
        INSERT INTO platform.support_ticket_comments(company_id,ticket_id,author_user_id,body,internal)
        VALUES (:company,:ticket,:actor,:body,:internal) RETURNING id
    """, company=target["company_id"], ticket=ticket_id, actor=actor.id, **data.model_dump()).scalar_one()
    audit(db, "support.reply", "support_ticket", ticket_id, company=target["company_id"], actor=actor.id,
          after={"comment_id": comment, "internal": data.internal})
    return {"id": comment}
