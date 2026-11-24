import { useState } from "react"
import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { PageHeading } from "../auth/AccessManagement"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import {
  DataTable, DataView, Pagination, Panel, Select, Status, TextArea, dateText, optionalValue, searchPath,
  statusName, textValue, useData, usePager,
} from "../platform/shared"
import type { Page } from "../platform/shared"
import { RecordEditor, RelatedRecords, StateEditor } from "./Catalog"
import { administrativeStatus, allowed, appPath, asText, catalogs, crm, optionsLabel, titleOf, valueFor } from "./model"
import type { Entry, Kind } from "./model"

type Child = "contacts" | "addresses" | "notes"
type Tab = { id: string; title: string; permission?: string }

const addressTypes = [["BILLING", "Facturación"], ["LEGAL", "Legal"], ["OTHER", "Otra"]] as [string, string][]
const childSpec: Record<Child, { title: string; singular: string; headers: string[] }> = {
  contacts: { title: "Contactos", singular: "contacto", headers: ["Nombre", "Cargo", "Teléfono", "Correo", "Principal"] },
  addresses: { title: "Direcciones", singular: "dirección", headers: ["Dirección", "Ciudad", "Tipo"] },
  notes: { title: "Notas", singular: "nota", headers: ["Fecha", "Autor", "Nota"] },
}

function ChildRecords({ id, child, account }: { id: string; child: Child; account: Account }) {
  const [editor, setEditor] = useState<Entry | "new" | null>(null)
  const pager = usePager()
  const endpoint = `${crm}/clients/${id}/${child}`
  const data = useData<Page<Entry>>("isp", searchPath(endpoint, pager.offset), pager.version)
  const canEdit = allowed(account, "clients.write")
  const spec = childSpec[child]
  const current = editor && editor !== "new" ? editor : undefined

  function values(row: Entry) {
    if (child === "contacts") return [row.name, row.position, row.phone, row.email, row.is_primary ? "Sí" : "No"]
    if (child === "addresses") return [row.address, row.city, optionsLabel(addressTypes, row.address_type)]
    return [dateText(asText(row, "created_at")), row.author, row.body]
  }

  return <Panel title={spec.title}>
    {canEdit && <div className="table-controls"><Button onClick={() => setEditor("new")}>Agregar {spec.singular}</Button></div>}
    {editor && canEdit && <div className="panel-body">
      <ActionForm key={current?.id ?? "new"} label="Guardar" cancel={() => setEditor(null)} submit={async (form) => {
        let payload
        if (child === "contacts") payload = {
          name: textValue(form, "name"), position: optionalValue(form, "position"), phone: optionalValue(form, "phone"),
          email: optionalValue(form, "email"), is_primary: form.has("is_primary"),
        }
        else if (child === "addresses") payload = {
          address: textValue(form, "address"), city: optionalValue(form, "city"), address_type: textValue(form, "address_type"),
        }
        else payload = { body: textValue(form, "body") }
        await api("isp", endpoint + (current ? "/" + current.id : ""), current ? "PUT" : "POST", payload)
        setEditor(null)
        pager.reload()
      }}>
        {child === "contacts" && <>
          <div className="form-grid">
            <Field label="Nombre del contacto" name="name" defaultValue={asText(current, "name")} required maxLength={120} />
            <Field label="Cargo" name="position" defaultValue={asText(current, "position")} maxLength={120} />
            <Field label="Teléfono del contacto" name="phone" type="tel" defaultValue={asText(current, "phone")} maxLength={30} />
            <Field label="Correo del contacto" name="email" type="email" defaultValue={asText(current, "email")} />
          </div>
          <label className="checkbox-label"><input name="is_primary" type="checkbox" defaultChecked={!!current?.is_primary} /> Contacto principal</label>
        </>}
        {child === "addresses" && <div className="form-grid">
          <Field label="Dirección" name="address" defaultValue={asText(current, "address")} maxLength={400} required />
          <Field label="Ciudad" name="city" defaultValue={asText(current, "city")} maxLength={120} />
          <Select label="Tipo de dirección" name="address_type" defaultValue={asText(current, "address_type") || "OTHER"}>
            {addressTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </Select>
        </div>}
        {child === "notes" && <TextArea label="Nota" name="body" required minLength={2} maxLength={4000} />}
      </ActionForm>
    </div>}
    <DataView state={data}>{({ items, has_more }) => <>
      <DataTable headers={[...spec.headers, ...(child !== "notes" && canEdit ? ["Acciones"] : [])]} empty={!items.length ? "Todavía no hay registros." : undefined}>
        {items.map((item) => <tr key={item.id}>
          {values(item).map((value, index) => <td key={index} className="wrap-cell">{value ?? "—"}</td>)}
          {canEdit && child !== "notes" && <td><Button onClick={() => setEditor(item)}>Editar</Button></td>}
        </tr>)}
      </DataTable>
      <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
    </>}</DataView>
  </Panel>
}

export function History({ kind, id }: { kind: "clients" | "services" | "devices"; id: string }) {
  const pager = usePager()
  const service = kind === "services"
  const state = useData<Page<Entry>>("isp", searchPath(`${crm}/${kind}/${id}/${service ? "history" : "activity"}`, pager.offset))
  return <Panel title={service ? "Historial de estados" : "Actividad administrativa"}>
    <DataView state={state}>{({ items, has_more }) => <>
      <DataTable headers={service ? ["Fecha", "Usuario", "Estado anterior", "Estado nuevo", "Motivo"] : ["Fecha", "Usuario", "Entidad", "Acción"]}
        empty={!items.length ? "Todavía no hay actividad registrada." : undefined}>
        {items.map((item) => <tr key={item.id}>
          <td>{dateText(asText(item, service ? "changed_at" : "occurred_at"))}</td><td>{item.actor || "Sistema"}</td>
          {service ? <>
            <td>{item.previous_status ? statusName(asText(item, "previous_status")) : "—"}</td>
            <td><Status value={asText(item, "new_status")} /></td><td className="wrap-cell">{item.reason || "—"}</td>
          </> : <><td>{item.entity_type}</td><td>{item.action}</td></>}
        </tr>)}
      </DataTable>
      <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
    </>}</DataView>
  </Panel>
}

const parameters = [
  ["interval_seconds", "Intervalo (s)", 5, 86400, "1"],
  ["timeout_ms", "Timeout (ms)", 100, 10000, "1"],
  ["packet_count", "Paquetes por comprobación", 1, 10, "1"],
  ["latency_warning_ms", "Latencia de aviso (ms)", 0.001, 999999999, "0.001"],
  ["loss_warning_pct", "Pérdida de aviso (%)", 0, 99.99, "0.01"],
  ["loss_failure_pct", "Tolerancia de pérdida (%)", 0, 99.99, "0.01"],
  ["failure_threshold", "Fallos consecutivos", 1, 32767, "1"],
  ["recovery_threshold", "Comprobaciones de recuperación", 1, 32767, "1"],
] as const

type Profile = Record<typeof parameters[number][0], number | string> & {
  requested: boolean; configured: boolean; minimum_interval_seconds: number
}

function Monitoring({ entry, account, complete }: { entry: Entry; account: Account; complete: () => void }) {
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const endpoint = `${crm}/devices/${entry.id}/icmp`
  const state = useData<Profile>("isp", endpoint, revision)
  return <>
    <Panel title="Configuración ICMP"><div className="panel-body">
      <p className="description">Estos valores se guardan para el futuro collector. En esta fase no se ejecutan comprobaciones.</p>
      <DataView state={state}>{(data) => editing
        ? <ActionForm label="Guardar configuración" cancel={() => setEditing(false)} submit={async (form) => {
          await api("isp", endpoint, "PUT", {
            requested: form.has("requested"),
            ...Object.fromEntries(parameters.map(([key]) => [key, Number(form.get(key))])),
          })
          setRevision((value) => value + 1)
          setEditing(false)
          complete()
        }}>
          <label className="checkbox-label"><input name="requested" type="checkbox" defaultChecked={data.requested} /> Solicitar monitoreo para este dispositivo</label>
          <div className="form-grid">{parameters.map(([key, label, min, max, step]) =>
            <Field key={key} label={label} name={key} type="number" required defaultValue={data[key]}
              min={key === "interval_seconds" ? Math.max(min, data.minimum_interval_seconds) : min} max={max} step={step} />)}</div>
        </ActionForm>
        : <>
          <dl className="profile-details">
            <dt>Estado de monitoreo</dt><dd><Status value={asText(entry, "monitoring_state")} /></dd>
            <dt>Intención de monitoreo</dt><dd>{data.requested ? "Solicitada" : "Deshabilitada"}</dd>
            <dt>Perfil</dt><dd>{data.configured ? "Guardado" : "Valores predeterminados"}</dd>
            {parameters.map(([key, label]) => <div className="detail-row" key={key}><dt>{label}</dt><dd>{data[key]}</dd></div>)}
          </dl>
          {allowed(account, "icmp.write") && !entry.retired_at && <div className="form-actions">
            <Button onClick={() => setEditing(true)}>Editar configuración ICMP</Button>
          </div>}
        </>}</DataView>
    </div></Panel>
    <Panel title="Mediciones e históricos"><div className="panel-body">
      <dl className="profile-details">
        {["Disponibilidad", "Latencia", "Pérdida de paquetes", "Última comprobación", "Incidentes", "Históricos"].map((label) =>
          <div className="detail-row" key={label}><dt>{label}</dt><dd>Sin datos</dd></div>)}
        <dt>SNMP</dt><dd>No disponible</dd>
      </dl>
    </div></Panel>
  </>
}

function General({ kind, entry, account }: { kind: Kind; entry: Entry; account: Account }) {
  const links: [Kind, string, string, string][] = [
    ["clients", "client_id", "client_name", "Cliente asociado"], ["sites", "site_id", "site_name", "Sitio"],
    ["internet-plans", "plan_id", "plan_name", "Plan de Internet"], ["devices", "access_router_id", "access_router_name", "Router de acceso"],
    ["services", "service_id", "service_plan_name", "Servicio asociado"],
  ]
  return <Panel title="Información general"><dl className="profile-details panel-body">
    <dt>Estado administrativo</dt><dd><Status value={administrativeStatus(kind, entry)} /></dd>
    <dt>Fecha de alta</dt><dd>{dateText(asText(entry, "created_at"))}</dd>
    {kind === "services" && <>
      <dt>Primera activación</dt><dd>{dateText(asText(entry, "activated_at"))}</dd>
      <dt>Cancelación</dt><dd>{dateText(asText(entry, "cancelled_at"))}</dd>
      <dt>Última observación de IP</dt><dd>{dateText(asText(entry, "service_ip_observed_at"))}</dd>
    </>}
    {catalogs[kind].fields.map((item) => <div className="detail-row" key={item.key}>
      <dt>{item.label}</dt><dd className="preserve-text">{item.options ? optionsLabel(item.options, entry[item.key]) : valueFor(entry, item.key) || "—"}</dd>
    </div>)}
    {links.filter(([, id]) => !!entry[id]).map(([target, id, name, label]) => <div className="detail-row" key={id}>
      <dt>{label}</dt><dd>{allowed(account, catalogs[target].permission + ".read")
        ? <a href={appPath(target, asText(entry, id))} className="platform-link">{entry[name] || "Consultar"}</a>
        : entry[name] || "Asociado"}</dd>
    </div>)}
  </dl></Panel>
}

export function CrmDetail({ kind, id, account }: { kind: Kind; id: string; account: Account }) {
  const [tab, setTab] = useState("general")
  const [form, setForm] = useState<"edit" | "state" | null>(null)
  const [revision, setRevision] = useState(0)
  const record = useData<Entry>("isp", `${crm}/${kind}/${id}`, revision)
  const spec = catalogs[kind]
  const choices: Tab[] = [{ id: "general", title: "Información general" }]
  if (kind === "clients") choices.push(
    { id: "contacts", title: "Contactos y direcciones" },
    { id: "services", title: "Servicios", permission: "services.read" },
    { id: "sites", title: "Sitios", permission: "sites.read" },
    { id: "devices", title: "Dispositivos", permission: "devices.read" },
    { id: "notes", title: "Notas e historial" },
    { id: "future", title: "Próximos módulos" },
  )
  if (kind === "sites") choices.push(
    { id: "services", title: "Servicios", permission: "services.read" },
    { id: "devices", title: "Dispositivos", permission: "devices.read" },
  )
  if (kind === "services") choices.push({ id: "history", title: "Historial", permission: "crm_history.read" })
  if (kind === "devices") choices.push(
    { id: "monitoring", title: "Monitoreo", permission: "icmp.read" },
    { id: "history", title: "Historial", permission: "crm_history.read" },
  )
  const visible = choices.filter((item) => !item.permission || allowed(account, item.permission))
  const current = visible.some((item) => item.id === tab) ? tab : "general"
  const refresh = () => setRevision((value) => value + 1)
  const saved = () => { setForm(null); refresh() }
  const relationFilter: Record<string, string> = kind === "clients" ? { client_id: id } : { site_id: id }

  return <>
    <a href={appPath(kind)} className="platform-link back-link">Volver a {spec.title.toLowerCase()}</a>
    <DataView state={record}>{(entry) => {
      const immutable = entry.retired_at || entry.status === "CLOSED"
      const canChangeState = allowed(account, spec.permission + ".status") && !immutable && entry.status !== "CANCELLED"
      return <>
        <PageHeading title={titleOf(kind, entry)} action={<div className="row-actions">
          {allowed(account, spec.permission + ".write") && !immutable && <Button onClick={() => setForm("edit")}>Editar</Button>}
          {canChangeState && <Button onClick={() => setForm("state")}>
            {kind === "services" ? "Cambiar estado" : administrativeStatus(kind, entry) === "ACTIVE" ? "Desactivar" : "Activar"}
          </Button>}
        </div>} />
        {form && <Panel title={form === "edit" ? "Editar " + spec.singular : "Cambiar estado administrativo"}><div className="panel-body">
          {form === "edit" ? <RecordEditor kind={kind} entry={entry} account={account} complete={saved} cancel={() => setForm(null)} />
            : <StateEditor kind={kind} entry={entry} complete={saved} cancel={() => setForm(null)} />}
        </div></Panel>}
        <div className="crm-tabs" aria-label="Secciones del detalle">
          {visible.map((item) => <button key={item.id} type="button" aria-pressed={current === item.id}
            onClick={() => setTab(item.id)}>{item.title}</button>)}
        </div>
        {current === "general" && <General kind={kind} entry={entry} account={account} />}
        {current === "contacts" && <><ChildRecords id={id} child="contacts" account={account} /><ChildRecords id={id} child="addresses" account={account} /></>}
        {current === "notes" && <><ChildRecords id={id} child="notes" account={account} />
          {allowed(account, "crm_history.read") && <History id={id} kind="clients" />}</>}
        {current === "history" && (kind === "services" || kind === "devices") && <History kind={kind} id={id} />}
        {(current === "services" || current === "sites" || current === "devices") &&
          <RelatedRecords key={current} kind={current} filter={relationFilter} account={account} />}
        {current === "monitoring" && <Monitoring entry={entry} account={account} complete={refresh} />}
        {current === "future" && <Panel title="Próximos módulos"><div className="panel-body">
          <p>Contratos, tickets de abonados, órdenes de trabajo, documentos, estado de cuenta, pagos e incidentes de monitoreo se incorporarán en fases posteriores.</p>
        </div></Panel>}
      </>
    }}</DataView>
  </>
}
