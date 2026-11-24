import { useState } from "react"
import { Plus } from "lucide-react"

import { api } from "../auth/api"
import type { Account, Scope } from "../auth/api"
import { PageHeading } from "../auth/AccessManagement"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import {
  DataTable, DataView, Pagination, Panel, Search, Select, Status, TextArea, dateText,
  optionalValue, searchPath, statusName, textValue, useData, usePager,
} from "./shared"
import type { Choice, Page } from "./shared"

const endpoint = "/support/tickets"
const basePath = (scope: Scope) => scope === "admin" ? "/admin/support" : "/app/support"
const priorities = ["LOW", "NORMAL", "HIGH", "CRITICAL"]
const statuses = ["OPEN", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "CANCELLED"]
const transitions: Record<string, string[]> = {
  OPEN: ["ASSIGNED", "IN_PROGRESS", "CANCELLED"],
  ASSIGNED: ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"],
  IN_PROGRESS: ["OPEN", "ASSIGNED", "RESOLVED", "CANCELLED"],
  RESOLVED: ["OPEN", "CLOSED"], CLOSED: ["OPEN"], CANCELLED: [],
}

type Ticket = {
  id: string; company_id: string; company_name: string; subject: string; priority: string; status: string
  opened_at: string; closed_at: string | null; origin: "USER" | "SYSTEM"
}
type Detail = Ticket & {
  description: string; assigned_staff_id?: string | null; closure_reason?: string | null
  comments: { id: string; body: string; internal: boolean; author: string; created_at: string }[]
  history: { id: string; previous_status: string | null; new_status: string; reason: string | null; actor: string | null; changed_at: string }[]
}

export function CreateTicket({ account }: { account: Account }) {
  const [created, setCreated] = useState(false)
  const canRead = account.permissions.includes("support.read")
  return <>
    {canRead && <a className="platform-link back-link" href="/app/support">Volver a solicitudes</a>}
    <PageHeading title="Contactar SKNet" description="Registra una solicitud para el equipo de soporte de SKNet." />
    <Panel><div className="panel-body">
      {created ? <p className="form-success" role="status">Solicitud registrada.</p>
        : <ActionForm label="Enviar solicitud" submit={async (fields) => {
          const result = await api<{ id: string }>("isp", endpoint, "POST", {
            subject: textValue(fields, "subject"), description: textValue(fields, "description"), priority: textValue(fields, "priority"),
          })
          if (canRead) window.location.assign(`/app/support/${result.id}`)
          else setCreated(true)
        }}>
          <div className="form-grid">
            <Field label="Asunto" name="subject" minLength={3} maxLength={160} required />
            <Select label="Prioridad" name="priority" defaultValue="NORMAL">
              {priorities.map((value) => <option key={value} value={value}>{statusName(value)}</option>)}
            </Select>
          </div>
          <TextArea label="Descripción" name="description" minLength={5} maxLength={5000} required />
        </ActionForm>}
    </div></Panel>
  </>
}

export function TicketList({ scope, account, automatic = false }: { scope: Scope; account: Account; automatic?: boolean }) {
  const [q, setQuery] = useState("")
  const [company, setCompany] = useState("")
  const [priority, setPriority] = useState("")
  const [status, setStatus] = useState("")
  const pager = usePager()
  const admin = scope === "admin"
  const companies = useData<Choice[]>("admin", admin ? "/companies/options" : null)
  const result = useData<Page<Ticket>>(scope, searchPath(endpoint, pager.offset, {
    q, company_id: company, priority, status, automatic: automatic ? "true" : "",
  }))
  return <>
    <PageHeading title={automatic ? "Tickets automáticos" : admin ? "Soporte SaaS" : "Soporte de SKNet"}
      description={automatic ? "Incidencias registradas por SKNet." : "Solicitudes entre las empresas ISP y SKNet."}
      action={!admin && account.permissions.includes("support.create") &&
        <a className="button button-primary" href="/app/support/new"><Plus size={15} /> Nueva solicitud</a>} />
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar por asunto" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} />
        {admin && <Select label="Empresa" value={company} onChange={(event) => { setCompany(event.target.value); pager.setOffset(0) }}>
          <option value="">Todas</option>{companies.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>}
        <Select label="Prioridad" value={priority} onChange={(event) => { setPriority(event.target.value); pager.setOffset(0) }}>
          <option value="">Todas</option>{priorities.map((value) => <option key={value} value={value}>{statusName(value)}</option>)}
        </Select>
        <Select label="Estado" value={status} onChange={(event) => { setStatus(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{statuses.map((value) => <option key={value} value={value}>{statusName(value)}</option>)}
        </Select>
      </div>
      {companies.error && <p className="panel-message form-error" role="alert">{companies.error}</p>}
      <DataView state={result}>{({ items, has_more }) => <>
        <DataTable headers={["Asunto", ...(admin ? ["Empresa"] : []), "Prioridad", "Estado", "Fecha"]}
          empty={!items.length ? "No hay solicitudes que coincidan." : undefined}>
          {items.map((item) => <tr key={item.id}>
            <td><a className="platform-link" href={`${basePath(scope)}/${item.id}`}>{item.subject}</a></td>
            {admin && <td>{item.company_name}</td>}
            <td><Status value={item.priority} /></td><td><Status value={item.status} /></td><td>{dateText(item.opened_at)}</td>
          </tr>)}
        </DataTable>
        <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

export function TicketDetail({ id, scope, account }: { id: string; scope: Scope; account: Account }) {
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const result = useData<Detail>(scope, `${endpoint}/${id}`, revision)
  const canEdit = scope === "admin" && account.permissions.includes("support.write")
  const canReply = account.permissions.includes("support.reply")
  const assignees = useData<Choice[]>("admin", canEdit ? "/support/assignees" : null, revision)

  return <>
    <a className="platform-link back-link" href={basePath(scope)}>Volver a soporte</a>
    <DataView state={result}>{(ticket) => {
      const closed = ["CLOSED", "CANCELLED"].includes(ticket.status)
      const assignee = assignees.data?.find((item) => item.id === ticket.assigned_staff_id)
      return <>
        <PageHeading title={ticket.subject} description={ticket.company_name}
          action={canEdit && <Button onClick={() => setEditing(true)}>Gestionar solicitud</Button>} />
        <Panel title="Detalle de la solicitud"><div className="panel-body">
          <p className="preserve-text">{ticket.description}</p>
          <dl className="profile-details">
            <dt>Estado</dt><dd><Status value={ticket.status} /></dd>
            <dt>Prioridad</dt><dd><Status value={ticket.priority} /></dd>
            <dt>Origen</dt><dd>{ticket.origin === "SYSTEM" ? "Sistema" : "Empresa"}</dd>
            <dt>Creada</dt><dd>{dateText(ticket.opened_at)}</dd>
            {ticket.closed_at && <><dt>Cierre</dt><dd>{dateText(ticket.closed_at)}</dd></>}
            {canEdit && <><dt>Responsable</dt><dd>{assignee?.name ?? (ticket.assigned_staff_id ? "Personal asignado" : "Sin asignar")}</dd></>}
          </dl>
        </div></Panel>
        {editing && canEdit && <Panel title="Asignación y estado"><div className="panel-body">
          <DataView state={assignees}>{(staff) => <ActionForm label="Guardar cambios" cancel={() => setEditing(false)} submit={async (fields) => {
            await api("admin", `${endpoint}/${id}`, "PUT", {
              priority: textValue(fields, "priority"), status: textValue(fields, "status"),
              assigned_staff_id: optionalValue(fields, "assigned_staff_id"), reason: textValue(fields, "reason"),
            })
            setEditing(false)
            setRevision((value) => value + 1)
          }}>
            <div className="form-grid">
              <Select label="Estado" name="status" defaultValue={ticket.status}>
                {[ticket.status, ...(transitions[ticket.status] ?? [])].map((value) =>
                  <option key={value} value={value}>{statusName(value)}</option>)}
              </Select>
              <Select label="Prioridad" name="priority" defaultValue={ticket.priority}>
                {priorities.map((value) => <option key={value} value={value}>{statusName(value)}</option>)}
              </Select>
              <Select label="Responsable" name="assigned_staff_id" defaultValue={ticket.assigned_staff_id ?? ""}>
                <option value="">Sin asignar</option>
                {ticket.assigned_staff_id && !assignee && <option value={ticket.assigned_staff_id}>Responsable actual</option>}
                {staff.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
              </Select>
              <Field label="Motivo de actualización" name="reason" minLength={2} maxLength={500} required />
            </div>
          </ActionForm>}</DataView>
        </div></Panel>}
        <Panel title="Respuestas">
          {ticket.comments.length ? <ul className="support-thread">{ticket.comments.map((comment) => <li key={comment.id}>
            <div><strong>{comment.author}</strong><span>{dateText(comment.created_at)}</span>{comment.internal && <small>Nota interna</small>}</div>
            <p className="preserve-text">{comment.body}</p>
          </li>)}</ul> : <p className="panel-message">Todavía no hay respuestas.</p>}
          {canReply && !closed && <div className="panel-body">
            <ActionForm key={revision} label="Enviar respuesta" submit={async (fields) => {
              await api(scope, `${endpoint}/${id}/replies`, "POST", {
                body: textValue(fields, "body"), internal: scope === "admin" && fields.has("internal"),
              })
              setRevision((value) => value + 1)
            }}>
              <TextArea label="Respuesta" name="body" minLength={2} maxLength={5000} required />
              {scope === "admin" && <label className="checkbox-label"><input type="checkbox" name="internal" /> Nota interna de SKNet</label>}
            </ActionForm>
          </div>}
        </Panel>
        <Panel title="Historial de estados">
          <DataTable headers={["Fecha", "Usuario", "Estado anterior", "Estado nuevo", ...(scope === "admin" ? ["Motivo"] : [])]}
            empty={!ticket.history.length ? "No hay cambios registrados." : undefined}>
            {ticket.history.map((entry) => <tr key={entry.id}>
              <td>{dateText(entry.changed_at)}</td><td>{entry.actor ?? "Sistema"}</td>
              <td>{entry.previous_status ? statusName(entry.previous_status) : "—"}</td><td><Status value={entry.new_status} /></td>
              {scope === "admin" && <td className="wrap-cell">{entry.reason || "—"}</td>}
            </tr>)}
          </DataTable>
        </Panel>
      </>
    }}</DataView>
  </>
}
