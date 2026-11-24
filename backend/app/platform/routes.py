from contextlib import contextmanager
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth.routes import database, write_operation
from app.auth.security import check_origin, principal
from app.auth.store import ISP, SAAS, row, rows
from app.platform import companies, plans, reporting, schemas, subscriptions, support


admin = APIRouter(prefix=SAAS.path, tags=["Plataforma SaaS"])
isp = APIRouter(prefix=ISP.path, tags=["Soporte de SKNet"])
Offset = Query(0, ge=0)
Limit = Query(30, ge=1, le=100)
Search = Query("", max_length=120)


@contextmanager
def read(request, permission=None, realm=SAAS):
    with database(request) as db:
        actor = principal(db, request, realm)
        if permission:
            actor.require(permission)
        yield db, actor


@contextmanager
def write(request, permission, realm=SAAS):
    check_origin(request)
    with database(request) as db, write_operation(db):
        actor = principal(db, request, realm)
        actor.require(permission)
        yield db, actor


def page(data, limit):
    return {"items": data[:limit], "has_more": len(data) > limit}


@admin.get("/dashboard")
def dashboard(request: Request):
    with read(request, "dashboard.read") as (db, actor):
        return reporting.dashboard(db, actor.permissions)


@admin.get("/companies")
def list_companies(request: Request, q: str = Search, status: schemas.CompanyStatus | None = None,
                   sort: Literal["name", "created", "status"] = "name",
                   direction: Literal["asc", "desc"] = "asc", offset: int = Offset, limit: int = Limit):
    with read(request, "companies.read") as (db, _):
        return page(companies.list_companies(db, q.strip(), status, sort, direction, offset, limit + 1), limit)


@admin.get("/companies/options")
def company_choices(request: Request):
    with read(request) as (db, actor):
        if not {"subscriptions.write", "support.read", "audit.read", "subscriptions.read"} & actor.permissions:
            raise HTTPException(403, "No tienes permiso para consultar empresas para este módulo.")
        return rows(db, "SELECT id,name FROM core.companies ORDER BY lower(name),id")


@admin.get("/companies/{company_id}")
def get_company(company_id: UUID, request: Request):
    with read(request, "companies.read") as (db, actor):
        entry = companies.company(db, company_id)
        result = dict(entry)
        if "subscriptions.read" in actor.permissions:
            result["subscription"] = subscriptions.current_for_company(db, company_id)
            result["usage"] = subscriptions.usage(db, company_id)
        return result


@admin.get("/companies/{company_id}/users")
def company_users(company_id: UUID, request: Request, q: str = Search, offset: int = Offset, limit: int = Limit):
    with read(request, "companies.users.read") as (db, _):
        companies.company(db, company_id)
        data = rows(db, """
            SELECT u.id,u.name,u.username,u.email,(u.active AND m.active) AS active
            FROM core.memberships m JOIN core.users u ON u.id=m.user_id
            WHERE m.company_id=:company AND strpos(lower(concat_ws(' ',u.name,u.username,u.email)),lower(:q))>0
            ORDER BY lower(u.name),u.id OFFSET :offset LIMIT :limit
        """, company=company_id, q=q.strip(), offset=offset, limit=limit + 1)
        return page(data, limit)


@admin.put("/companies/{company_id}")
def edit_company(company_id: UUID, data: schemas.CompanyWrite, request: Request):
    with write(request, "companies.write") as (db, actor):
        return companies.edit(db, actor, company_id, data)


@admin.patch("/companies/{company_id}/status")
def company_status(company_id: UUID, data: schemas.CompanyState, request: Request):
    with write(request, "companies.write") as (db, actor):
        return companies.set_status(db, actor, company_id, data)


@admin.get("/plans")
def list_plans(request: Request, q: str = Search, active: bool | None = None,
               offset: int = Offset, limit: int = Limit):
    with read(request, "plans.read") as (db, _):
        return page(plans.list_plans(db, q.strip(), active, offset, limit + 1), limit)


@admin.get("/plans/features")
def list_features(request: Request):
    with read(request, "plans.read") as (db, _):
        return plans.features(db)


@admin.get("/plans/choices")
def plan_options(request: Request):
    with read(request) as (db, actor):
        if not {"plans.read", "settings.read", "settings.write", "subscriptions.write"} & actor.permissions:
            raise HTTPException(403, "No tienes permiso para seleccionar planes.")
        return plans.choices(db)


@admin.post("/plans", status_code=201)
def create_plan(data: schemas.PlanCreate, request: Request):
    with write(request, "plans.write") as (db, actor):
        return plans.save(db, actor, data)


@admin.get("/plans/{plan_id}")
def get_plan(plan_id: UUID, request: Request):
    with read(request, "plans.read") as (db, _):
        return plans.plan(db, plan_id)


@admin.put("/plans/{plan_id}")
def edit_plan(plan_id: UUID, data: schemas.PlanEdit, request: Request):
    with write(request, "plans.write") as (db, actor):
        return plans.save(db, actor, data, plan_id)


@admin.patch("/plans/{plan_id}/status")
def plan_status(plan_id: UUID, data: schemas.PlanState, request: Request):
    with write(request, "plans.write") as (db, actor):
        return plans.set_active(db, actor, plan_id, data.active)


@admin.get("/subscriptions")
def list_subscriptions(request: Request, company_id: UUID | None = None,
                       status: schemas.SubscriptionStatus | None = None, q: str = Search,
                       offset: int = Offset, limit: int = Limit):
    with read(request, "subscriptions.read") as (db, _):
        return page(subscriptions.list_subscriptions(db, company_id, status, q.strip(), offset, limit + 1), limit)


@admin.post("/companies/{company_id}/subscriptions", status_code=201)
def add_subscription(company_id: UUID, data: schemas.SubscriptionWrite, request: Request):
    with write(request, "subscriptions.write") as (db, actor):
        return subscriptions.assign(db, actor, company_id, data)


@admin.get("/subscriptions/{subscription_id}")
def get_subscription(subscription_id: UUID, request: Request):
    with read(request, "subscriptions.read") as (db, _):
        return subscriptions.subscription_detail(db, subscription_id)


@admin.put("/subscriptions/{subscription_id}")
def edit_subscription(subscription_id: UUID, data: schemas.SubscriptionWrite, request: Request):
    with write(request, "subscriptions.write") as (db, actor):
        return subscriptions.change(db, actor, subscription_id, data)


@admin.get("/support/tickets")
def admin_tickets(request: Request, company_id: UUID | None = None,
                  priority: schemas.Priority | None = None, status: schemas.TicketStatus | None = None,
                  q: str = Search, offset: int = Offset, limit: int = Limit, automatic: bool = False):
    with read(request, "support.read") as (db, _):
        return page(support.list_tickets(db, company_id, priority, status, q.strip(), offset, limit + 1,
                                         automatic=automatic), limit)


@admin.get("/support/assignees")
def assignees(request: Request):
    with read(request, "support.write") as (db, _):
        return support.staff_choices(db)


@isp.get("/support/tickets")
def isp_tickets(request: Request, priority: schemas.Priority | None = None,
                status: schemas.TicketStatus | None = None, q: str = Search,
                offset: int = Offset, limit: int = Limit):
    with read(request, "support.read", ISP) as (db, actor):
        return page(support.list_tickets(db, actor.company, priority, status, q.strip(), offset, limit + 1), limit)


@isp.post("/support/tickets", status_code=201)
def create_ticket(data: schemas.TicketCreate, request: Request):
    with write(request, "support.create", ISP) as (db, actor):
        return support.create(db, actor, data)


@admin.get("/support/tickets/{ticket_id}")
def admin_ticket(ticket_id: UUID, request: Request):
    with read(request, "support.read") as (db, actor):
        return support.detail(db, actor, ticket_id)


@isp.get("/support/tickets/{ticket_id}")
def isp_ticket(ticket_id: UUID, request: Request):
    with read(request, "support.read", ISP) as (db, actor):
        return support.detail(db, actor, ticket_id)


@admin.put("/support/tickets/{ticket_id}")
def update_ticket(ticket_id: UUID, data: schemas.TicketEdit, request: Request):
    with write(request, "support.write") as (db, actor):
        return support.update(db, actor, ticket_id, data)


@admin.post("/support/tickets/{ticket_id}/replies", status_code=201)
def admin_reply(ticket_id: UUID, data: schemas.TicketReply, request: Request):
    with write(request, "support.reply") as (db, actor):
        return support.reply(db, actor, ticket_id, data)


@isp.post("/support/tickets/{ticket_id}/replies", status_code=201)
def isp_reply(ticket_id: UUID, data: schemas.TicketReply, request: Request):
    with write(request, "support.reply", ISP) as (db, actor):
        return support.reply(db, actor, ticket_id, data)


@admin.get("/audit")
def audit_records(request: Request, company_id: UUID | None = None,
                  scope: Literal["ISP", "SAAS", "SYSTEM"] | None = None,
                  action: str | None = Query(None, max_length=80), q: str = Search,
                  offset: int = Offset, limit: int = Limit):
    with read(request, "audit.read") as (db, _):
        return page(reporting.audit_events(db, company_id, scope, action, q.strip(), offset, limit + 1), limit)
