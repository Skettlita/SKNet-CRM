import { useState } from "react"
import { Plus } from "lucide-react"

import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { PageHeading } from "../auth/AccessManagement"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import {
  DataTable, DataView, Pagination, Panel, ResourceUsage, Search, Select, Status, amountText, dateText,
  searchPath, statusName, textValue, useData, usePager,
} from "./shared"
import type { Choice, Page, PlanChoice, Subscription, Usage } from "./shared"

const statuses = ["TRIAL", "ACTIVE", "GRACE", "SUSPENDED", "CANCELLED"]

type History = {
  id: string; changed_at: string; actor: string | null; previous_status: string | null; new_status: string
  previous_plan: string | null; previous_version: number | null; new_plan: string; new_version: number
  previous_starts_at: string | null; previous_ends_at: string | null
  new_starts_at: string | null; new_ends_at: string | null; reason: string | null
}
type Detail = Subscription & { usage: Usage; history: History[] }

function localInput(value: string | null | undefined) {
  if (!value) return ""
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function Editor({ subscription, onDone, onCancel }: {
  subscription?: Subscription; onDone: (id: string) => void; onCancel: () => void
}) {
  const company = useData<Choice[]>("admin", subscription ? null : "/companies/options")
  const plans = useData<PlanChoice[]>("admin", "/plans/choices")
  const [expiration, setExpiration] = useState(subscription ? subscription.ends_at ? "date" : "none" : "default")
  const error = plans.error || company.error
  if (error) return <p className="form-error" role="alert">{error}</p>
  if (!plans.data || !subscription && !company.data) return <p role="status">Cargando opciones…</p>
  if (!subscription && (!company.data?.length || !plans.data.length)) return <p>Se necesita una empresa y un plan habilitado.</p>

  const activeVersionPresent = plans.data.some((plan) => plan.version_id === subscription?.plan_version_id)
  return <ActionForm label={subscription ? "Guardar cambios" : "Asignar suscripción"} cancel={onCancel} submit={async (fields) => {
    const companyId = textValue(fields, "company_id")
    const start = textValue(fields, "starts_at")
    const chosenEnd = textValue(fields, "ends_at")
    const startChanged = start && start !== localInput(subscription?.starts_at)
    const endChanged = expiration === "date" && chosenEnd !== localInput(subscription?.ends_at)
    const body = {
      plan_version_id: textValue(fields, "plan_version_id"),
      status: textValue(fields, "status"),
      ...(startChanged ? { starts_at: new Date(start).toISOString() } : {}),
      ...(expiration === "none" ? { ends_at: null } : endChanged ? { ends_at: new Date(chosenEnd).toISOString() } : {}),
      reason: textValue(fields, "reason"),
    }
    const outcome = await api<{ id: string }>("admin", subscription ? `/subscriptions/${subscription.id}` : `/companies/${companyId}/subscriptions`,
      subscription ? "PUT" : "POST", body)
    onDone(outcome.id)
  }}>
    <div className="form-grid">
      {!subscription && <Select label="Empresa" name="company_id" required defaultValue="">
        <option value="" disabled>Selecciona una empresa</option>
        {company.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </Select>}
      <Select label="Versión del plan" name="plan_version_id" required defaultValue={subscription?.plan_version_id ?? ""}>
        <option value="" disabled>Selecciona una versión</option>
        {subscription && !activeVersionPresent && <option value={subscription.plan_version_id}>
          {subscription.plan_name} · v{subscription.plan_version} (asignada)
        </option>}
        {plans.data.map((plan) => <option key={plan.version_id} value={plan.version_id}>{plan.name} · v{plan.version}</option>)}
      </Select>
      <Select label="Estado de suscripción" name="status" defaultValue={subscription?.status ?? "ACTIVE"}>
        {statuses.filter((value) => subscription || value !== "CANCELLED")
          .map((value) => <option key={value} value={value}>{statusName(value)}</option>)}
      </Select>
      <Field label="Fecha de inicio" name="starts_at" type="datetime-local" defaultValue={localInput(subscription?.starts_at)} />
      <Select label="Vencimiento" value={expiration} onChange={(event) => setExpiration(event.target.value)}>
        {!subscription && <option value="default">Duración del plan</option>}
        <option value="none">Sin vencimiento</option><option value="date">Fecha específica</option>
      </Select>
      {expiration === "date" && <Field label="Fecha de vencimiento" name="ends_at" type="datetime-local"
        defaultValue={localInput(subscription?.ends_at)} required />}
    </div>
    <Field label="Motivo del cambio" name="reason" minLength={2} maxLength={500} required />
  </ActionForm>
}

export function SubscriptionList({ account }: { account: Account }) {
  const [adding, setAdding] = useState(false)
  const [q, setQuery] = useState("")
  const [status, setStatus] = useState("")
  const pager = usePager()
  const result = useData<Page<Subscription>>("admin", searchPath("/subscriptions", pager.offset, { q, status }))
  return <>
    <PageHeading title="Suscripciones" description="Asignaciones, vigencia e historial de planes por empresa."
      action={account.permissions.includes("subscriptions.write") && <Button variant="primary" onClick={() => setAdding(true)}><Plus size={15} /> Asignar plan</Button>} />
    {adding && <Panel title="Asignar suscripción"><div className="panel-body">
      <Editor onCancel={() => setAdding(false)} onDone={(id) => window.location.assign(`/admin/subscriptions/${id}`)} />
    </div></Panel>}
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar empresa o plan" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} />
        <Select label="Estado" value={status} onChange={(event) => { setStatus(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{statuses.map((item) => <option key={item} value={item}>{statusName(item)}</option>)}
        </Select>
      </div>
      <DataView state={result}>{({ items, has_more }) => <>
        <DataTable headers={["Empresa", "Plan", "Versión", "Estado", "Inicio", "Vencimiento"]}
          empty={!items.length ? "No hay suscripciones que coincidan." : undefined}>
          {items.map((item) => <tr key={item.id}>
            <td><a className="platform-link" href={`/admin/subscriptions/${item.id}`}>{item.company_name}</a></td>
            <td>{item.plan_name}</td><td>{item.plan_version}</td><td><Status value={item.status} /></td>
            <td>{dateText(item.starts_at)}</td><td>{item.ends_at ? dateText(item.ends_at) : "Sin vencimiento"}</td>
          </tr>)}
        </DataTable>
        <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

export function SubscriptionDetail({ id, account }: { id: string; account: Account }) {
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const result = useData<Detail>("admin", `/subscriptions/${id}`, revision)
  return <>
    <a href="/admin/subscriptions" className="platform-link back-link">Volver a suscripciones</a>
    <DataView state={result}>{(item) => <>
      <PageHeading title={item.company_name} description="Detalle de la suscripción SaaS."
        action={account.permissions.includes("subscriptions.write") && item.status !== "CANCELLED" &&
          <Button onClick={() => setEditing(true)}>Editar suscripción</Button>} />
      {editing && <Panel title="Cambiar plan o vigencia"><div className="panel-body">
        <p>Un cambio de plan conserva los registros existentes, incluso si superan el nuevo límite.</p>
        <Editor subscription={item} onCancel={() => setEditing(false)} onDone={() => {
          setEditing(false); setRevision((value) => value + 1)
        }} />
      </div></Panel>}
      <div className="platform-columns">
        <Panel title="Condiciones asignadas"><dl className="profile-details panel-body">
          <dt>Plan</dt><dd>{item.plan_name} · Versión {item.plan_version}</dd>
          <dt>Precio</dt><dd>{amountText(item.price, item.currency)} · {item.billing_period === "YEARLY" ? "Anual" : "Mensual"}</dd>
          <dt>Estado</dt><dd><Status value={item.status} /></dd>
          <dt>Vigencia actual</dt><dd>{item.current ? "Vigente" : "Fuera de vigencia"}</dd>
          <dt>Inicio</dt><dd>{dateText(item.starts_at)}</dd>
          <dt>Vencimiento</dt><dd>{item.ends_at ? dateText(item.ends_at) : "Sin vencimiento"}</dd>
          <dt>Intervalo mínimo ICMP</dt><dd>{item.min_poll_interval_seconds ?? "—"}</dd>
          <dt>Retención (días)</dt><dd>{item.retention_days ?? "—"}</dd>
        </dl></Panel>
        <Panel title="Utilización actual"><ResourceUsage usage={item.usage} subscription={item} /></Panel>
      </div>
      <Panel title="Historial de cambios">
        <DataTable headers={["Fecha", "Usuario", "Plan anterior", "Plan nuevo", "Estado", "Inicio / vencimiento", "Motivo"]}
          empty={!item.history.length ? "La suscripción todavía no tiene cambios registrados." : undefined}>
          {item.history.map((entry) => <tr key={entry.id}>
            <td>{dateText(entry.changed_at)}</td><td>{entry.actor ?? "Sistema"}</td>
            <td>{entry.previous_plan ? `${entry.previous_plan} v${entry.previous_version}` : "—"}</td>
            <td>{entry.new_plan} v{entry.new_version}</td><td><Status value={entry.new_status} /></td>
            <td>{dateText(entry.new_starts_at)} / {entry.new_starts_at ? entry.new_ends_at ? dateText(entry.new_ends_at) : "Sin vencimiento" : "—"}</td>
            <td className="wrap-cell">{entry.reason || "—"}</td>
          </tr>)}
        </DataTable>
      </Panel>
    </>}</DataView>
  </>
}
