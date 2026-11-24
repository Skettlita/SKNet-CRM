import { useState } from "react"
import { Plus } from "lucide-react"

import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { PageHeading } from "../auth/AccessManagement"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import {
  DataTable, DataView, Pagination, Panel, ResourceUsage, Search, Select, Status,
  dateText, optionalValue, searchPath, statusName, textValue, useData, usePager,
} from "./shared"
import type { Page, Subscription, Usage } from "./shared"

type Company = {
  id: string; name: string; tax_id: string | null; email: string | null; phone: string | null; timezone: string
  status: string; connectivity: string; provisioning_status: string | null; created_at: string
  plan_name: string | null; subscription_status: string | null; subscription?: Subscription | null; usage?: Usage
}

type CompanyUser = { id: string; name: string; username: string; email: string; active: boolean }

export function CompanyList({ account }: { account: Account }) {
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState("")
  const [sort, setSort] = useState("name")
  const [direction, setDirection] = useState("asc")
  const pager = usePager()
  const companies = useData<Page<Company>>("admin", searchPath("/companies", pager.offset, { q: query, status, sort, direction }))

  return <>
    <PageHeading title="Empresas" description="Empresas ISP registradas en SKNet."
      action={account.permissions.includes("companies.create") && <a className="button button-primary" href="/admin/companies/new">
        <Plus size={15} /> Nueva empresa</a>} />
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar empresas" value={query} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} />
        <Select label="Estado administrativo" value={status} onChange={(event) => { setStatus(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{["ACTIVE", "INACTIVE", "CLOSED"].map((value) => <option key={value} value={value}>{statusName(value)}</option>)}
        </Select>
        <Select label="Ordenar por" value={sort} onChange={(event) => { setSort(event.target.value); pager.setOffset(0) }}>
          <option value="name">Empresa</option><option value="created">Fecha de alta</option><option value="status">Estado</option>
        </Select>
        <Select label="Dirección" value={direction} onChange={(event) => { setDirection(event.target.value); pager.setOffset(0) }}>
          <option value="asc">Ascendente</option><option value="desc">Descendente</option>
        </Select>
      </div>
      <DataView state={companies}>{({ items, has_more }) => <>
        <DataTable headers={["Empresa", "NIT", "Estado administrativo", "Conectividad", "Plan", "Fecha de alta"]}
          empty={!items.length ? "No hay empresas que coincidan." : undefined}>
          {items.map((item) => <tr key={item.id}>
            <td><a className="platform-link" href={`/admin/companies/${item.id}`}>{item.name}</a></td>
            <td>{item.tax_id || "—"}</td><td><Status value={item.status} /></td>
            <td><Status value={item.connectivity} /></td><td>{item.plan_name ?? "Sin suscripción"}</td><td>{dateText(item.created_at)}</td>
          </tr>)}
        </DataTable>
        <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

function Users({ id }: { id: string }) {
  const [q, setQuery] = useState("")
  const pager = usePager()
  const users = useData<Page<CompanyUser>>("admin", searchPath(`/companies/${id}/users`, pager.offset, { q }))
  return <Panel title="Usuarios de la empresa">
    <div className="table-controls"><Search label="Buscar usuarios" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} /></div>
    <DataView state={users}>{({ items, has_more }) => <>
      <DataTable headers={["Nombre", "Usuario", "Correo", "Estado"]} empty={!items.length ? "No se encontraron usuarios." : undefined}>
        {items.map((user) => <tr key={user.id}><td>{user.name}</td><td>{user.username}</td>
          <td>{user.email}</td><td><Status value={user.active ? "ACTIVE" : "INACTIVE"} /></td></tr>)}
      </DataTable>
      <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
    </>}</DataView>
  </Panel>
}

export function CompanyDetail({ id, account }: { id: string; account: Account }) {
  const [version, setVersion] = useState(0)
  const [form, setForm] = useState<"edit" | "state" | null>(null)
  const company = useData<Company>("admin", `/companies/${id}`, version)
  const canWrite = account.permissions.includes("companies.write")
  function done() { setForm(null); setVersion((value) => value + 1) }

  return <>
    <a className="platform-link back-link" href="/admin/companies">Volver a empresas</a>
    <DataView state={company}>{(item) => <>
      <PageHeading title={item.name} action={canWrite && <div className="row-actions">
        <Button onClick={() => setForm("edit")}>Editar empresa</Button>
        {item.status !== "CLOSED" && <Button onClick={() => setForm("state")}>{item.status === "ACTIVE" ? "Suspender" : "Activar"}</Button>}
      </div>} />
      {form && <Panel title={form === "edit" ? "Información empresarial" : "Cambiar estado administrativo"}>
        <div className="panel-body">
          {form === "edit" ? <ActionForm label="Guardar cambios" cancel={() => setForm(null)} submit={async (fields) => {
            await api("admin", `/companies/${id}`, "PUT", {
              name: textValue(fields, "name"), tax_id: optionalValue(fields, "tax_id"), email: optionalValue(fields, "email"),
              phone: optionalValue(fields, "phone"), timezone: textValue(fields, "timezone"),
            })
            done()
          }}>
            <div className="form-grid">
              <Field label="Empresa" name="name" defaultValue={item.name} minLength={2} maxLength={120} required />
              <Field label="NIT" name="tax_id" defaultValue={item.tax_id ?? ""} maxLength={40} />
              <Field label="Correo empresarial" name="email" type="email" defaultValue={item.email ?? ""} />
              <Field label="Teléfono" name="phone" type="tel" defaultValue={item.phone ?? ""} maxLength={30} />
              <Field label="Zona horaria IANA" name="timezone" defaultValue={item.timezone} maxLength={80} required />
            </div>
          </ActionForm> : <ActionForm label={item.status === "ACTIVE" ? "Suspender empresa" : "Activar empresa"}
            cancel={() => setForm(null)} submit={async (fields) => {
              await api("admin", `/companies/${id}/status`, "PATCH", {
                status: item.status === "ACTIVE" ? "INACTIVE" : "ACTIVE", reason: textValue(fields, "reason"),
              })
              done()
            }}>
              <p className="description">La suspensión conserva los datos y bloquea el acceso de los usuarios de esta empresa.</p>
              <Field label="Motivo" name="reason" minLength={2} maxLength={500} required />
            </ActionForm>}
        </div>
      </Panel>}
      <div className="platform-columns">
        <Panel title="Información empresarial"><dl className="profile-details panel-body">
          <dt>NIT</dt><dd>{item.tax_id || "—"}</dd><dt>Correo</dt><dd>{item.email || "—"}</dd>
          <dt>Teléfono</dt><dd>{item.phone || "—"}</dd><dt>Zona horaria</dt><dd>{item.timezone}</dd>
          <dt>Estado administrativo</dt><dd><Status value={item.status} /></dd>
          <dt>Conectividad</dt><dd><Status value={item.connectivity} /></dd>
        </dl></Panel>
        {item.usage && <Panel title="Plan y utilización">
          <div className="panel-body">
            {item.subscription ? <a className="platform-link" href={`/admin/subscriptions/${item.subscription.id}`}>
              {item.subscription.plan_name} · Versión {item.subscription.plan_version}</a> : <p>Sin suscripción.</p>}
          </div>
          <ResourceUsage usage={item.usage} subscription={item.subscription ?? null} />
        </Panel>}
      </div>
      {account.permissions.includes("companies.users.read") && <Users id={id} />}
    </>}</DataView>
  </>
}
