import { useState } from "react"
import { Plus } from "lucide-react"

import type { Account } from "../auth/api"
import { api } from "../auth/api"
import { PageHeading } from "../auth/AccessManagement"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import {
  DataTable, DataView, Pagination, Panel, Search, Select, Status, TextArea, amountText, dateText,
  integerValue, searchPath, textValue, useData, usePager,
} from "./shared"
import type { Page } from "./shared"

type Feature = { code: string; name: string; implemented: boolean }
type Terms = {
  version_id: string; version: number; effective_at: string; description: string; price: number | string; currency: string
  billing_period: "MONTHLY" | "YEARLY"; duration_days: number | null; max_clients: number | null
  max_users: number | null; max_devices: number | null; min_poll_interval_seconds: number | null
  retention_days: number | null; features: string[]
}
type Plan = { id: string; code: string; name: string; active: boolean; is_default: boolean; versions: Terms[] }
type Summary = Omit<Plan, "versions"> & Terms

const fields = [
  ["duration_days", "Duración en días", 1, 36500], ["max_clients", "Máximo de clientes", 1, 2147483647],
  ["max_users", "Máximo de usuarios activos", 1, 2147483647], ["max_devices", "Máximo de dispositivos monitoreados", 1, 2147483647],
  ["min_poll_interval_seconds", "Intervalo mínimo ICMP (segundos)", 5, 86400],
  ["retention_days", "Retención de monitoreo (días)", 1, 36500],
] as const

function Editor({ plan, features, complete, cancel }: {
  plan?: Plan; features: Feature[]; complete: (plan: Plan) => void; cancel?: () => void
}) {
  const current = plan?.versions[0]
  return <ActionForm label="Guardar plan" cancel={cancel} submit={async (data) => {
    const payload = {
      name: textValue(data, "name"), description: textValue(data, "description"),
      price: textValue(data, "price"), currency: textValue(data, "currency"),
      billing_period: textValue(data, "billing_period"), features: data.getAll("features"),
      ...Object.fromEntries(fields.map(([key]) => [key, integerValue(data, key)])),
      ...(plan ? {} : { code: textValue(data, "code").toUpperCase() }),
    }
    complete(await api<Plan>("admin", plan ? `/plans/${plan.id}` : "/plans", plan ? "PUT" : "POST", payload))
  }}>
    <div className="form-grid">
      {!plan && <Field label="Código" name="code" minLength={2} maxLength={40} required />}
      <Field label="Nombre" name="name" defaultValue={plan?.name} minLength={2} maxLength={120} required />
      <Field label="Precio por periodo" name="price" type="number" defaultValue={current?.price ?? "0"} min={0} step="0.01" required />
      <Field label="Moneda (código de 3 letras)" name="currency" defaultValue={current?.currency ?? "BOB"} minLength={3} maxLength={3} required />
      <Select label="Periodicidad" name="billing_period" defaultValue={current?.billing_period ?? "MONTHLY"}>
        <option value="MONTHLY">Mensual</option><option value="YEARLY">Anual</option>
      </Select>
      {fields.map(([key, label, min, max]) => <Field key={key} label={label} name={key} type="number"
        min={min} max={max} defaultValue={current?.[key] ?? ""} />)}
    </div>
    <TextArea label="Descripción" name="description" maxLength={2000} defaultValue={current?.description} />
    <p className="description">Deja la duración y los límites en blanco para no fijar un vencimiento o un máximo. Los parámetros de monitoreo se guardan para cuando el módulo esté disponible.</p>
    <div className="permission-group"><strong>Funcionalidades</strong>
      {features.map((feature) => <label className="checkbox-label" key={feature.code}>
        <input type="checkbox" name="features" value={feature.code} disabled={!feature.implemented}
          defaultChecked={feature.implemented && (current?.features.includes(feature.code) ?? feature.code === "ACCESS")} />
        {feature.name}{!feature.implemented && " · No disponible"}
      </label>)}
    </div>
  </ActionForm>
}

export function PlanList({ account }: { account: Account }) {
  const [q, setQuery] = useState("")
  const [active, setActive] = useState("")
  const pager = usePager()
  const state = useData<Page<Summary>>("admin", searchPath("/plans", pager.offset, { q, active }))
  return <>
    <PageHeading title="Planes SaaS" description="Condiciones de suscripción a SKNet para empresas ISP."
      action={account.permissions.includes("plans.write") && <a className="button button-primary" href="/admin/plans/new"><Plus size={15} /> Nuevo plan</a>} />
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar planes" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} />
        <Select label="Estado" value={active} onChange={(event) => { setActive(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option><option value="true">Habilitados</option><option value="false">Desactivados</option>
        </Select>
      </div>
      <DataView state={state}>{({ items, has_more }) => <>
        <DataTable headers={["Plan SaaS", "Código", "Versión", "Precio", "Periodicidad", "Duración", "Estado"]}
          empty={!items.length ? "No hay planes que coincidan." : undefined}>
          {items.map((plan) => <tr key={plan.id}>
            <td><a href={`/admin/plans/${plan.id}`} className="platform-link">{plan.name}</a>{plan.is_default && " · Predeterminado"}</td>
            <td>{plan.code}</td><td>{plan.version}</td><td>{amountText(plan.price, plan.currency)}</td>
            <td>{plan.billing_period === "YEARLY" ? "Anual" : "Mensual"}</td>
            <td>{plan.duration_days ? `${plan.duration_days} días` : "Indefinida"}</td>
            <td><Status value={plan.active ? "ENABLED" : "PLAN_OFF"} /></td>
          </tr>)}
        </DataTable>
        <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

export function NewPlan() {
  const features = useData<Feature[]>("admin", "/plans/features")
  return <>
    <a href="/admin/plans" className="platform-link back-link">Volver a planes</a>
    <PageHeading title="Nuevo plan SaaS" />
    <Panel><div className="panel-body"><DataView state={features}>{(features) => <Editor features={features}
      complete={(plan) => window.location.assign(`/admin/plans/${plan.id}`)} />}</DataView></div></Panel>
  </>
}

export function PlanDetail({ id, account }: { id: string; account: Account }) {
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const [statusForm, setStatusForm] = useState(false)
  const [chosen, setChosen] = useState("")
  const plan = useData<Plan>("admin", `/plans/${id}`, revision)
  const features = useData<Feature[]>("admin", "/plans/features")
  const canWrite = account.permissions.includes("plans.write")
  function done() { setEditing(false); setStatusForm(false); setChosen(""); setRevision((value) => value + 1) }

  return <>
    <a href="/admin/plans" className="platform-link back-link">Volver a planes</a>
    <DataView state={plan}>{(item) => {
      const current = item.versions.find((version) => version.version_id === chosen) ?? item.versions[0]
      return <>
        <PageHeading title={item.name} description={item.code + (item.is_default ? " · Plan predeterminado" : "")}
          action={canWrite && <div className="row-actions">
            <Button onClick={() => { setEditing(true); setStatusForm(false) }}>Editar plan</Button>
            {(!item.active || !item.is_default) && <Button onClick={() => { setStatusForm(true); setEditing(false) }}>
              {item.active ? "Desactivar" : "Activar"}
            </Button>}
          </div>} />
        {editing && <Panel title="Editar condiciones"><div className="panel-body">
          <DataView state={features}>{(catalog) => <Editor plan={item} features={catalog} complete={done} cancel={() => setEditing(false)} />}</DataView>
        </div></Panel>}
        {statusForm && <Panel title={item.active ? "Desactivar plan" : "Activar plan"}><div className="panel-body">
          <ActionForm label={item.active ? "Desactivar plan" : "Activar plan"} cancel={() => setStatusForm(false)} submit={async () => {
            await api("admin", `/plans/${id}/status`, "PATCH", { active: !item.active })
            done()
          }}><p>Las suscripciones asignadas conservan las condiciones de su versión.</p></ActionForm>
        </div></Panel>}
        <Panel title="Versiones y condiciones">
          <div className="table-controls"><Select label="Versión" value={current.version_id} onChange={(event) => setChosen(event.target.value)}>
            {item.versions.map((version) => <option key={version.version_id} value={version.version_id}>v{version.version} · {dateText(version.effective_at)}</option>)}
          </Select></div>
          <dl className="profile-details panel-body">
            <dt>Estado comercial</dt><dd><Status value={item.active ? "ENABLED" : "PLAN_OFF"} /></dd>
            <dt>Descripción</dt><dd className="preserve-text">{current.description || "—"}</dd>
            <dt>Precio</dt><dd>{amountText(current.price, current.currency)} · {current.billing_period === "YEARLY" ? "Anual" : "Mensual"}</dd>
            {fields.map(([key, label]) => <div key={key} className="detail-row"><dt>{label}</dt>
              <dd>{current[key] ?? (key === "duration_days" ? "Indefinida" : "Sin configurar")}</dd></div>)}
            <dt>Funcionalidades</dt><dd>{features.data?.filter((feature) => feature.implemented && current.features.includes(feature.code))
              .map((feature) => feature.name).join(", ") || "Ninguna disponible"}</dd>
          </dl>
        </Panel>
      </>
    }}</DataView>
  </>
}
