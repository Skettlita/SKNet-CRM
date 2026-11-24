import { useState } from "react"
import { Plus } from "lucide-react"

import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { PageHeading } from "../auth/AccessManagement"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import { DataTable, DataView, Pagination, Panel, Search, Select, Status, searchPath, textValue, useData, usePager } from "../platform/shared"
import type { Page } from "../platform/shared"
import {
  Fields, Relation, administrativeStatus, allowed, appPath, asText, catalogs, crm, optionsLabel, payload, serviceStates, titleOf,
} from "./model"
import type { Entry, Kind } from "./model"

export function RecordEditor({ kind, entry, account, cancel, complete }: {
  kind: Kind; entry?: Entry; account: Account; cancel: () => void; complete: (record: Entry) => void
}) {
  const spec = catalogs[kind]
  const [client, setClient] = useState(asText(entry, "client_id"))
  const [site, setSite] = useState(asText(entry, "site_id"))
  const [plan, setPlan] = useState(asText(entry, "plan_id"))
  const [device, setDevice] = useState(asText(entry, "access_router_id"))
  const [service, setService] = useState(asText(entry, "service_id"))
  const [siteKind, setSiteKind] = useState(asText(entry, "site_type"))
  const [access, setAccess] = useState(asText(entry, "access_method"))
  const editing = entry !== undefined
  const fields = spec.fields.filter((item) => item.key !== "pppoe_username" || access === "PPPOE")

  return <ActionForm label="Guardar" cancel={cancel} submit={async (data) => {
    const input = payload(fields, data)
    if (kind === "services") Object.assign(input, {
      client_id: client, site_id: site, plan_id: plan, access_router_id: device || null,
      ...(access === "STATIC" ? { ip_assignment: "FIXED" } : {}),
    })
    if (kind === "sites") input.client_id = siteKind === "CLIENT_SITE" ? client : null
    if (kind === "devices") Object.assign(input, { site_id: site, service_id: service || null })
    const endpoint = `${crm}/${kind}${editing ? "/" + entry.id : ""}`
    complete(await api<Entry>("isp", endpoint, editing ? "PUT" : "POST", input))
  }}>
    {kind === "services" && <div className="form-grid crm-relations">
      <Relation kind="clients" label="Cliente" name="client_id" value={client} known={asText(entry, "client_name")}
        account={account} required filters={{ status: "ACTIVE" }} change={(value) => { setClient(value); setSite("") }} />
      {client && <Relation key={client} kind="sites" label="Sitio de instalación" name="site_id" value={site} known={asText(entry, "site_name")}
        account={account} required filters={{ client_id: client, status: "ACTIVE" }} change={setSite} />}
      <Relation kind="internet-plans" label="Plan de Internet" name="plan_id" value={plan} known={asText(entry, "plan_name")}
        account={account} required filters={{ status: "ACTIVE" }} change={setPlan} />
      <Relation kind="devices" label="Router de acceso" name="access_router_id" value={device} known={asText(entry, "access_router_name")}
        account={account} filters={{ status: "ACTIVE" }} change={setDevice} />
    </div>}
    {kind === "devices" && <div className="form-grid crm-relations">
      <Relation kind="sites" label="Sitio" name="site_id" value={site} known={asText(entry, "site_name")}
        account={account} required filters={{ status: "ACTIVE" }} change={(value) => { setSite(value); setService("") }} />
      {site && <Relation key={site} kind="services" label="Servicio asociado" name="service_id" value={service} known={asText(entry, "service_plan_name")}
        account={account} filters={{ site_id: site }} change={setService} />}
    </div>}
    <Fields fields={fields} row={entry} values={{ site_type: siteKind, access_method: access }}
      onChange={(key, value) => {
        if (key === "site_type") setSiteKind(value)
        if (key === "access_method") setAccess(value)
      }} />
    {kind === "sites" && siteKind === "CLIENT_SITE" && <Relation kind="clients" name="client_id" label="Cliente asociado"
      value={client} known={asText(entry, "client_name")} required account={account} change={setClient} />}
    {kind === "services" && <p className="description">El precio y la moneda se toman del plan si se dejan vacíos al contratar. La IP del servicio es informativa y se registra aparte de la IP de gestión.</p>}
  </ActionForm>
}

const basicStates = [["ACTIVE", "Activo"], ["INACTIVE", "Inactivo"]] as const

export function RecordRows({ kind, entries, empty, account }: { kind: Kind; entries: Entry[]; empty: string; account: Account }) {
  const spec = catalogs[kind]
  const showMonitor = kind === "devices" && allowed(account, "icmp.read")
  return <DataTable headers={[kind === "services" ? "Cliente y plan" : "Nombre", ...spec.columns.map(([name]) => name),
    "Estado administrativo", ...(showMonitor ? ["Monitoreo"] : [])]} empty={!entries.length ? empty : undefined}>
    {entries.map((item) => <tr key={item.id}>
      <td><a className="platform-link" href={appPath(kind, item.id)}>{titleOf(kind, item)}</a></td>
      {spec.columns.map(([column, render]) => <td key={column} className="wrap-cell">{render(item)}</td>)}
      <td><Status value={administrativeStatus(kind, item)} /></td>
      {showMonitor && <td><Status value={asText(item, "monitoring_state")} /></td>}
    </tr>)}
  </DataTable>
}

export function RelatedRecords({ kind, account, filter }: { kind: Kind; account: Account; filter: Record<string, string> }) {
  const pager = usePager()
  const data = useData<Page<Entry>>("isp", searchPath(`${crm}/${kind}`, pager.offset, filter))
  return <Panel title={catalogs[kind].title}>
    <DataView state={data}>{({ items, has_more }) => <>
      <RecordRows kind={kind} entries={items} empty="No hay registros asociados." account={account} />
      <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
    </>}</DataView>
  </Panel>
}

export function CrmCatalog({ kind, account }: { kind: Kind; account: Account }) {
  const spec = catalogs[kind]
  const [showForm, setShowForm] = useState(false)
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const [category, setCategory] = useState("")
  const [order, setOrder] = useState("name")
  const [direction, setDirection] = useState("asc")
  const pager = usePager()
  const state = useData<Page<Entry>>("isp", searchPath(`${crm}/${kind}`, pager.offset, {
    q: search, status, category, sort: order, direction,
  }), pager.version)
  const statuses = kind === "services" ? serviceStates : [...basicStates, ...(kind === "clients" ? [["CLOSED", "Cerrado"]] : [])]
  return <>
    <PageHeading title={spec.title} description={kind === "internet-plans" ? "Catálogo de Internet que tu empresa ofrece a sus clientes." : undefined}
      action={allowed(account, spec.permission + ".create") && <Button variant="primary" onClick={() => setShowForm(true)}>
        <Plus size={14} />Registrar {spec.singular}
      </Button>} />
    {showForm && <Panel title={"Registrar " + spec.singular}><div className="panel-body">
      <RecordEditor kind={kind} account={account} cancel={() => setShowForm(false)} complete={(record) => {
        window.location.assign(appPath(kind, record.id))
      }} />
    </div></Panel>}
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar registros" value={search} onChange={(event) => { setSearch(event.target.value); pager.setOffset(0) }} />
        <Select label="Estado administrativo" value={status} onChange={(event) => { setStatus(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{statuses.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </Select>
        {spec.categories.length > 0 && <Select label={spec.categoryLabel ?? "Tipo"} value={category}
          onChange={(event) => { setCategory(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{spec.categories.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </Select>}
        <Select label="Ordenar por" value={order} onChange={(event) => { setOrder(event.target.value); pager.setOffset(0) }}>
          <option value="name">Nombre</option><option value="created">Fecha de alta</option><option value="status">Estado</option>
        </Select>
        <Select label="Dirección del orden" value={direction} onChange={(event) => { setDirection(event.target.value); pager.setOffset(0) }}>
          <option value="asc">Ascendente</option><option value="desc">Descendente</option>
        </Select>
      </div>
      <DataView state={state}>{({ items, has_more }) => <>
        <RecordRows kind={kind} entries={items} empty="No hay registros que coincidan." account={account} />
        <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

const transitions: Record<string, string[]> = {
  PENDING: ["ACTIVE", "CANCELLED"], ACTIVE: ["SUSPENDED", "CANCELLED"], SUSPENDED: ["ACTIVE", "CANCELLED"], CANCELLED: [],
}

export function StateEditor({ kind, entry, cancel, complete }: { kind: Kind; entry: Entry; cancel: () => void; complete: () => void }) {
  const [next, setNext] = useState("")
  const isService = kind === "services"
  const state = administrativeStatus(kind, entry)
  const enable = state !== "ACTIVE"
  return <ActionForm label={isService ? "Confirmar cambio" : enable ? "Confirmar activación" : "Confirmar desactivación"}
    cancel={cancel} submit={async (fields) => {
      const activation = textValue(fields, "activated_at")
      await api("isp", `${crm}/${kind}/${entry.id}/status`, "PATCH", {
        ...(isService ? { status: next, ...(activation ? { activated_at: new Date(activation).toISOString() } : {}) } : { active: enable }),
        reason: textValue(fields, "reason"),
      })
      complete()
    }}>
    {isService ? <>
      <Select label="Nuevo estado" value={next} required onChange={(event) => setNext(event.target.value)}>
        <option value="">Selecciona…</option>
        {(transitions[state] ?? []).map((value) => <option key={value} value={value}>{optionsLabel(serviceStates, value)}</option>)}
      </Select>
      {next === "ACTIVE" && !entry.activated_at && <Field label="Fecha y hora de activación" name="activated_at" type="datetime-local" />}
      {next === "CANCELLED" && <p>La cancelación conserva el servicio y su historial. Es un estado final.</p>}
    </> : <p>Este cambio conserva el registro y las relaciones existentes.</p>}
    <Field label="Motivo del cambio" name="reason" minLength={2} maxLength={500} required />
  </ActionForm>
}
