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
  Fields, Relation, administrativeStatus, allowed, appPath, asText, capabilities, catalogs, codeFields, crm,
  deviceCategories, optionsLabel, payload, serviceStates, siteCategories, siteTypes, siteTypesByCategory, titleOf,
} from "./model"
import type { Entry, Kind } from "./model"
import { CustomerRegistration, ServiceFields, SiteFields, serviceInput } from "./Registration"

export function RecordEditor({ kind, entry, account, cancel, complete }: {
  kind: Kind; entry?: Entry; account: Account; cancel: () => void; complete: (record: Entry) => void
}) {
  const spec = catalogs[kind]
  const [client, setClient] = useState(asText(entry, "client_id"))
  const [site, setSite] = useState(asText(entry, "site_id"))
  const [service, setService] = useState(asText(entry, "service_id"))
  const [siteKind, setSiteKind] = useState(asText(entry, "site_type"))
  const [siteCategory, setSiteCategory] = useState(asText(entry, "site_category"))
  const [deviceCategory, setDeviceCategory] = useState(asText(entry, "device_category"))
  const [linkedAddress, setLinkedAddress] = useState(asText(entry, "client_address_id"))
  const codeField = codeFields[kind]
  const editing = entry !== undefined
  const customerEquipment = deviceCategory === "CUSTOMER_EQUIPMENT"
  const selectedCapabilities = Array.isArray(entry?.capabilities) ? entry.capabilities : []

  if (kind === "clients" && !editing) return <CustomerRegistration account={account} cancel={cancel} complete={complete} />

  return <ActionForm label="Guardar" cancel={cancel} submit={async (data) => {
    const input = kind === "services" ? { ...serviceInput(data), client_id: client, site_id: site } : payload(spec.fields, data)
    if (kind === "sites") Object.assign(input, {
      client_id: siteCategory === "CUSTOMER" ? client : null, site_category: siteCategory,
      client_address_id: linkedAddress || null,
    })
    if (kind === "devices") Object.assign(input, {
      site_id: site, device_category: deviceCategory, client_id: customerEquipment ? client : null,
      service_id: customerEquipment ? service || null : null,
      capabilities: customerEquipment ? [] : data.getAll("capabilities"),
    })
    const endpoint = `${crm}/${kind}${editing ? "/" + entry.id : ""}`
    complete(await api<Entry>("isp", endpoint, editing ? "PUT" : "POST", input))
  }}>
    {editing && codeField && <Field label="Código comercial" value={asText(entry, codeField)} readOnly />}
    {kind === "services" && <>
      <div className="form-grid crm-relations">
        <Relation kind="clients" label="Cliente" name="client_id" value={client} known={asText(entry, "client_name")}
          account={account} required filters={{ status: "ACTIVE" }} change={(value) => { setClient(value); setSite("") }} />
        {client && <Relation key={client} kind="sites" label="Sitio de instalación" name="site_id" value={site} known={asText(entry, "site_name")}
          account={account} required filters={{ client_id: client, status: "ACTIVE" }} change={setSite} />}
      </div>
      <ServiceFields account={account} entry={entry} />
    </>}
    {kind === "sites" && <>
      <Select label="Categoría del sitio" value={siteCategory} required onChange={(event) => {
        setSiteCategory(event.target.value); setSiteKind(""); setClient(""); setLinkedAddress("")
      }}>
        <option value="">Selecciona…</option>
        {siteCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </Select>
      <SiteFields entry={entry} category={siteCategory} siteType={siteKind} sameAddress={!!linkedAddress} changeType={setSiteKind} />
      {siteCategory === "CUSTOMER" && <Relation kind="clients" name="client_id" label="Cliente asociado"
        value={client} known={asText(entry, "client_name")} required account={account}
        change={(value) => { setClient(value); setLinkedAddress("") }} />}
      {!!linkedAddress && <p className="description">Dirección vinculada del cliente · {asText(entry, "effective_address")}
        {" "}<Button type="button" onClick={() => setLinkedAddress("")}>Usar otra dirección</Button>
      </p>}
    </>}
    {kind === "devices" && <>
      <Select label="Categoría funcional" value={deviceCategory} required onChange={(event) => {
        setDeviceCategory(event.target.value); setClient(""); setSite(""); setService("")
      }}>
        <option value="">Selecciona…</option>
        {deviceCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </Select>
      <div className="form-grid crm-relations">
        {customerEquipment && <Relation kind="clients" label="Cliente" name="client_id" value={client}
          known={asText(entry, "client_name")} account={account} required filters={{ status: "ACTIVE" }}
          change={(value) => { setClient(value); setSite(""); setService("") }} />}
        {(deviceCategory === "INFRASTRUCTURE" || (customerEquipment && client)) && <Relation key={deviceCategory + client}
          kind="sites" label="Sitio" name="site_id" value={site} known={asText(entry, "site_name")} account={account} required
          filters={customerEquipment ? { status: "ACTIVE", client_id: client } : { status: "ACTIVE", isp_site: "true" }}
          change={(value) => { setSite(value); setService("") }} />}
        {customerEquipment && site && allowed(account, "services.read") && <Relation key={site} kind="services"
          label="Servicio asociado" name="service_id" value={service} known={asText(entry, "service_plan_name")}
          account={account} filters={{ site_id: site, client_id: client, linkable_service: "true" }} change={setService} />}
      </div>
      {deviceCategory === "INFRASTRUCTURE" && <fieldset className="crm-capabilities">
        <legend>Capacidades técnicas</legend>
        {capabilities.map(([value, label]) => <label className="checkbox-label" key={value}>
          <input type="checkbox" name="capabilities" value={value} defaultChecked={selectedCapabilities.includes(value)} /> {label}
        </label>)}
      </fieldset>}
      <Fields fields={spec.fields} row={entry} />
    </>}
    {(kind === "clients" || kind === "internet-plans") && <Fields fields={spec.fields} row={entry} />}
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
    <div className="table-controls"><a className="platform-link" href={appPath(kind)}>Abrir {catalogs[kind].title.toLowerCase()}</a></div>
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
  const [siteType, setSiteType] = useState("")
  const [deviceCategory, setDeviceCategory] = useState("")
  const [order, setOrder] = useState("name")
  const [direction, setDirection] = useState("asc")
  const pager = usePager()
  const state = useData<Page<Entry>>("isp", searchPath(`${crm}/${kind}`, pager.offset, {
    q: search, status, category, site_type: siteType, device_category: deviceCategory, sort: order, direction,
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
    {kind === "sites" && <div className="crm-tabs" aria-label="Categorías de sitios">
      {[["", "Todos los sitios"], ...siteCategories].map(([value, label]) => <button type="button" key={value}
        aria-pressed={category === value} onClick={() => { setCategory(value); setSiteType(""); pager.setOffset(0) }}>{label}</button>)}
    </div>}
    <Panel>
      <div className="table-controls platform-filters">
        <Search label={kind === "sites" ? "Buscar por nombre, código o cliente" : "Buscar registros"}
          value={search} onChange={(event) => { setSearch(event.target.value); pager.setOffset(0) }} />
        <Select label="Estado administrativo" value={status} onChange={(event) => { setStatus(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{statuses.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </Select>
        {spec.categories.length > 0 && <Select label={spec.categoryLabel ?? "Tipo"} value={category}
          onChange={(event) => { setCategory(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{spec.categories.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </Select>}
        {kind === "sites" && <Select label="Tipo de sitio" value={siteType}
          onChange={(event) => { setSiteType(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>
          {(siteTypesByCategory[category] ?? siteTypes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>}
        {kind === "devices" && <Select label="Categoría funcional" value={deviceCategory}
          onChange={(event) => { setDeviceCategory(event.target.value); pager.setOffset(0) }}>
          <option value="">Todas</option>
          {deviceCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
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
