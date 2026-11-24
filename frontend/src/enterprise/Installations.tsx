import { useState } from "react"
import { PageHeading } from "../auth/AccessManagement"
import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import { DataTable, DataView, Panel, Pagination, Search, Select, Status, TextArea, dateText, optionalValue,
  searchPath, textValue, useData, usePager } from "../platform/shared"
import type { Page } from "../platform/shared"
import { allowed, asText, Relation, crm } from "./model"
import type { Entry } from "./model"
import { ServiceFields, serviceInput } from "./Registration"
import { CatalogFields } from "./Inventory"

const orders = crm + "/installations"
const path = "/app/installations"
const stages: Record<string, string> = { PENDING: "Pendiente", SCHEDULED: "Programada",
  IN_PROGRESS: "En ejecución", COMPLETED: "Completada", CANCELLED: "Cancelada", ARCHIVED: "Archivada" }
const changes: Record<string, string[]> = { PENDING: ["SCHEDULED", "IN_PROGRESS", "CANCELLED"],
  SCHEDULED: ["SCHEDULED", "IN_PROGRESS", "CANCELLED"], IN_PROGRESS: ["COMPLETED", "CANCELLED"] }
const priorities: Record<string, string> = { LOW: "Baja", NORMAL: "Normal", HIGH: "Alta", CRITICAL: "Crítica" }
type Choice = { id: string; name: string }
type Order = Entry & { technicians: Choice[]; devices: Entry[]; history: {
  actor: string; action: string; occurred_at: string; new_status: string; detail: string | null
}[] }

export function CreateInstallation({ account, serviceId, cancel }: { account: Account; serviceId?: string; cancel: () => void }) {
  const [service, setService] = useState(serviceId ?? "")
  return <Panel title="Nueva instalación"><div className="panel-body">
    <ActionForm label="Crear orden" cancel={cancel} submit={async (form) => {
      const order = await api<Entry>("isp", orders, "POST", { service_id: service,
        priority: textValue(form, "priority"), observations: optionalValue(form, "observations"), reason: textValue(form, "reason") })
      window.location.assign(path + "/" + order.id)
    }}>
      {!serviceId && <Relation kind="services" name="service_id" label="Servicio pendiente" value={service} required
        account={account} filters={{ status: "PENDING" }} change={setService} />}
      <Priority />
      <TextArea label="Observaciones" name="observations" maxLength={4000} />
      <Field label="Motivo" name="reason" minLength={2} maxLength={500} required />
    </ActionForm>
  </div></Panel>
}

function Priority({ value = "NORMAL" }: { value?: string }) {
  return <Select name="priority" label="Prioridad" defaultValue={value}>
    {Object.entries(priorities).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
  </Select>
}

function iso(form: FormData, key: string) {
  const value = textValue(form, key)
  return value ? new Date(value).toISOString() : null
}

function localDate(value: string) {
  if (!value) return ""
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function InstallationList({ account }: { account: Account }) {
  const pager = usePager()
  const [editing, setEditing] = useState(false)
  const [q, setQuery] = useState("")
  const [status, setStatus] = useState("")
  const state = useData<Page<Entry>>("isp", searchPath(orders, pager.offset, { q, status }), 0, 10000)
  return <>
    <PageHeading title="Instalaciones" action={allowed(account, "installations.create") && allowed(account, "services.read") &&
      <Button variant="primary" onClick={() => setEditing(true)}>Nueva instalación</Button>} />
    {editing && <CreateInstallation account={account} cancel={() => setEditing(false)} />}
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar por código, cliente o sitio" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} />
        <Select label="Estado" value={status} onChange={(event) => { setStatus(event.target.value); pager.setOffset(0) }}>
          <option value="">Operativas</option>{Object.entries(stages).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </Select>
      </div>
      <DataView state={state}>{({ items, has_more }) => <>
        <DataTable headers={["Código", "Cliente", "Sitio", "Servicio", "Prioridad", "Estado", "Programada"]}
          empty={!items.length ? "No hay instalaciones que coincidan." : undefined}>
          {items.map((order) => <tr key={order.id}>
            <td><a className="platform-link" href={path + "/" + order.id}>{order.installation_code}</a></td>
            <td>{order.client_name}</td><td>{order.site_name}</td><td>{order.service_code}</td>
            <td><Status value={asText(order, "priority")} /></td>
            <td>{stages[order.archived_at ? "ARCHIVED" : asText(order, "status")]}</td>
            <td>{dateText(asText(order, "scheduled_at"))}</td>
          </tr>)}
        </DataTable><Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

function AttachEquipment({ account }: { account: Account }) {
  const [device, setDevice] = useState("")
  const [create, setCreate] = useState(false)
  const [mode, setMode] = useState("NONE")
  return <>
    {allowed(account, "devices.create") && <label className="checkbox-label"><input type="checkbox" name="create_device" checked={create}
      onChange={(event) => setCreate(event.target.checked)} /> Registrar equipo en esta orden</label>}
    {create ? <div className="form-grid">
      <Field name="equipment_name" label="Nombre del equipo" minLength={2} required />
      <CatalogFields account={account} />
      <Field name="serial_number" label="Número de serie" />
    </div> : <Relation kind="devices" label="Equipo disponible" name="device_id" value={device}
      account={account} required filters={{ device_category: "CUSTOMER_EQUIPMENT", assignment_state: "AVAILABLE" }} change={setDevice} />}
    <label className="checkbox-label"><input name="link_service" type="checkbox" defaultChecked /> Vincular al servicio de la orden</label>
    <Select name="ip_mode" label="Origen de IP de gestión" value={mode} onChange={(event) => setMode(event.target.value)}>
      <option value="NONE">Sin IP</option><option value="INDEPENDENT">Independiente</option><option value="SERVICE">Heredada del servicio</option>
    </Select>
    {mode === "INDEPENDENT" && <Field label="IPv4 de gestión" name="ip_address" required />}
  </>
}

function OrderForm({ account, order, action, cancel, complete }: {
  account: Account; order: Order; action: string; cancel: () => void; complete: () => void
}) {
  const { technicians, devices, history, ...service } = order
  const [next, setNext] = useState("")
  const [activation, setActivation] = useState(allowed(account, "services.status"))
  const choices = useData<Choice[]>("isp", action === "manage" ? orders + "/technicians" : null)
  const title = { manage: "Programación y técnicos", status: "Estado de la instalación", service: "Datos técnicos del servicio",
    devices: "Equipo de la orden", archive: "Archivar instalación", delete: "Eliminar borrador" }[action] ?? action
  return <Panel title={title}><div className="panel-body">
    <ActionForm label={action === "delete" ? "Confirmar eliminación" : "Guardar"} cancel={cancel} submit={async (form) => {
      const reason = textValue(form, "reason")
      if (action === "manage") await api("isp", orders + "/" + order.id, "PUT", {
        priority: textValue(form, "priority"), scheduled_at: iso(form, "scheduled_at"),
        technician_ids: form.getAll("technician_ids"), technical_notes: optionalValue(form, "technical_notes"), observations: optionalValue(form, "observations"),
      })
      if (action === "status") await api("isp", orders + "/" + order.id + "/status", "POST", {
        status: next, reason, scheduled_at: iso(form, "scheduled_at"), verification: optionalValue(form, "verification"),
        activate_service: activation, monitor_devices: form.getAll("monitor_devices"),
      })
      if (action === "service") await api("isp", orders + "/" + order.id + "/service", "PUT", serviceInput(form))
      if (action === "devices") await api("isp", orders + "/" + order.id + "/devices", "POST", {
        reason, device_id: optionalValue(form, "device_id"), link_service: form.has("link_service"),
        ip_mode: textValue(form, "ip_mode"), ip_address: optionalValue(form, "ip_address"),
        ...(form.has("create_device") ? { new_device: { name: textValue(form, "equipment_name"),
          type_id: textValue(form, "type_id"), manufacturer_id: optionalValue(form, "manufacturer_id"),
          model_id: optionalValue(form, "model_id"), serial_number: optionalValue(form, "serial_number") } } : {}),
      })
      if (action === "archive") await api("isp", orders + "/" + order.id + "/archive", "POST", { reason })
      if (action === "delete") {
        await api("isp", orders + "/" + order.id, "DELETE", { reason, confirmed: form.has("confirmed") })
        window.location.assign(path)
      } else complete()
    }}>
      {action === "manage" && <>
        <div className="form-grid"><Priority value={asText(order, "priority")} />
          <Field label="Fecha programada" name="scheduled_at" type="datetime-local" defaultValue={localDate(asText(order, "scheduled_at"))} /></div>
        <DataView state={choices}>{(people) => <Select name="technician_ids" label="Técnicos" multiple size={Math.min(5, Math.max(2, people.length))}
          defaultValue={order.technicians.map(({ id }) => id)}>{people.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}</Select>}</DataView>
        <TextArea label="Observaciones" name="observations" defaultValue={asText(order, "observations")} />
        <TextArea label="Datos técnicos de la orden" name="technical_notes" defaultValue={asText(order, "technical_notes")} />
      </>}
      {action === "status" && <>
        <Select name="status" label="Nuevo estado" value={next} required onChange={(event) => setNext(event.target.value)}>
          <option value="">Selecciona…</option>
          {(changes[asText(order, "status")] ?? []).filter((value) => value === "COMPLETED"
            ? allowed(account, "installations.complete") : allowed(account, "installations.write"))
            .map((value) => <option key={value} value={value}>{stages[value]}</option>)}
        </Select>
        {next === "SCHEDULED" && <Field label="Fecha programada" name="scheduled_at" type="datetime-local"
          required defaultValue={localDate(asText(order, "scheduled_at"))} />}
        {next === "COMPLETED" && <>
          <TextArea label="Resultado de verificación manual o técnica" name="verification" required maxLength={4000} />
          {allowed(account, "services.status") && <label className="checkbox-label"><input type="checkbox"
            checked={activation} onChange={(event) => setActivation(event.target.checked)} /> Activar el servicio</label>}
          {allowed(account, "icmp.write") && order.devices.filter((item) => item.effective_ip).map((item) =>
            <label className="checkbox-label" key={item.id}><input type="checkbox" name="monitor_devices" value={item.id} /> Monitorear {item.name}</label>)}
        </>}
      </>}
      {action === "service" && <ServiceFields account={account} entry={{ ...service, technical_notes: service.service_notes }} />}
      {action === "devices" && <AttachEquipment account={account} />}
      {!(["manage", "service"].includes(action)) && <Field name="reason" label="Motivo" minLength={2} maxLength={500} required />}
      {action === "delete" && <label className="checkbox-label"><input type="checkbox" name="confirmed" required /> Confirmo la eliminación definitiva.</label>}
    </ActionForm>
  </div></Panel>
}

function InstallationDetail({ id, account }: { id: string; account: Account }) {
  const pager = usePager()
  const [action, show] = useState("")
  const state = useData<Order>("isp", orders + "/" + id, pager.version)
  return <><a className="platform-link back-link" href={path}>Volver a instalaciones</a>
    <DataView state={state}>{(order) => {
      const open = Boolean(changes[asText(order, "status")]) && !order.archived_at
      const edit = open && allowed(account, "installations.write")
      return <>
        <PageHeading title={asText(order, "installation_code")} action={<div className="row-actions">
          {edit && <Button onClick={() => show("manage")}>Programación y técnicos</Button>}
          {open && (edit || order.status === "IN_PROGRESS" && allowed(account, "installations.complete")) &&
            <Button onClick={() => show("status")}>Cambiar estado</Button>}
          {edit && allowed(account, "services.write") && <Button onClick={() => show("service")}>Editar datos del servicio</Button>}
          {edit && allowed(account, "devices.write") && <Button onClick={() => show("devices")}>Agregar equipo</Button>}
          {!open && !order.archived_at && allowed(account, "installations.archive") && <Button onClick={() => show("archive")}>Archivar</Button>}
          {order.status === "PENDING" && allowed(account, "installations.delete") && <Button onClick={() => show("delete")}>Eliminar borrador</Button>}
        </div>} />
        {action && <OrderForm key={action} action={action} account={account} order={order} cancel={() => show("")}
          complete={() => { show(""); pager.reload() }} />}
        <Panel title="Orden de instalación"><dl className="profile-details panel-body">
          <dt>Estado</dt><dd>{stages[order.archived_at ? "ARCHIVED" : asText(order, "status")]}</dd>
          <dt>Cliente</dt><dd>{order.client_name}</dd><dt>Sitio</dt><dd>{order.site_name} · {order.address || "Sin dirección"}</dd>
          <dt>Servicio</dt><dd>{order.service_code} · {order.plan_name}</dd><dt>Modalidad</dt><dd>{order.access_method}</dd>
          <dt>Router de acceso</dt><dd>{order.access_router_name || "Sin asignar"}</dd>
          <dt>Programada</dt><dd>{dateText(asText(order, "scheduled_at"))}</dd><dt>Finalizada</dt><dd>{dateText(asText(order, "completed_at"))}</dd>
          <dt>Técnicos</dt><dd>{order.technicians.map(({ name }) => name).join(", ") || "Sin asignar"}</dd>
          <dt>Observaciones</dt><dd>{order.observations || "—"}</dd><dt>Datos técnicos</dt><dd>{order.technical_notes || "—"}</dd>
          <dt>Verificación</dt><dd>{order.verification || "Pendiente"}</dd>
        </dl></Panel>
        <Panel title="Equipos"><DataTable headers={["Equipo", "Código", "Situación", "IP de gestión"]} empty={!order.devices.length ? "Sin equipos." : undefined}>
          {order.devices.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.device_code}</td>
            <td>{item.assignment_state}</td><td>{item.effective_ip || "Sin IP"}</td></tr>)}
        </DataTable></Panel>
        <Panel title="Historial"><DataTable headers={["Fecha", "Operador", "Operación", "Estado", "Detalle"]}
          empty={!order.history.length ? "Todavía no hay cambios." : undefined}>
          {order.history.map((item, index) => <tr key={index}><td>{dateText(item.occurred_at)}</td><td>{item.actor}</td>
            <td>{item.action}</td><td>{stages[item.new_status]}</td><td>{item.detail || "—"}</td></tr>)}
        </DataTable></Panel>
      </>
    }}</DataView>
  </>
}

export function Installations({ account, id }: { account: Account; id?: string }) {
  return id ? <InstallationDetail id={id} account={account} /> : <InstallationList account={account} />
}
