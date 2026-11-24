import { useState } from "react"
import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { ActionForm, Field } from "../auth/forms"
import { DataTable, DataView, Panel, Pagination, Select, dateText, optionalValue, searchPath, textValue, useData, usePager } from "../platform/shared"
import type { Page } from "../platform/shared"
import { Relation, asText, crm, optionsLabel } from "./model"
import type { Entry } from "./model"

export const assignmentStates = [["AVAILABLE", "Disponible"], ["ASSIGNED", "Asignado"],
  ["INSTALLED", "Instalado"], ["MAINTENANCE", "En mantenimiento"], ["RETIRED", "Retirado"]] as [string, string][]
export const ipModes = [["NONE", "Sin IP"], ["INDEPENDENT", "IP independiente"], ["SERVICE", "Heredada del servicio"]] as [string, string][]
export const ownershipOptions = [["UNKNOWN", "Sin definir"], ["ISP", "ISP"], ["CUSTOMER", "Abonado"],
  ["THIRD_PARTY", "Tercero"]] as [string, string][]

export function placementInput(form: FormData) {
  return { site_id: optionalValue(form, "site_id"), service_id: optionalValue(form, "service_id"),
    client_id: optionalValue(form, "client_id"), ip_address: optionalValue(form, "ip_address"),
    ip_mode: textValue(form, "ip_mode") || "NONE", assignment_state: textValue(form, "assignment_state") || "AVAILABLE" }
}

export function PlacementFields({ account, category, entry, clientId, siteId, startAssigned = false }: {
  account: Account; category: string; entry?: Entry; clientId?: string; siteId?: string; startAssigned?: boolean
}) {
  const [client, setClient] = useState(clientId || asText(entry, "client_id"))
  const [site, setSite] = useState(siteId || asText(entry, "site_id"))
  const [service, setService] = useState(asText(entry, "service_id"))
  const [mode, setMode] = useState(asText(entry, "ip_mode") || "NONE")
  const [state, setState] = useState(asText(entry, "assignment_state") !== "AVAILABLE" && entry
    ? asText(entry, "assignment_state") : startAssigned ? "ASSIGNED" : "AVAILABLE")
  const finalEquipment = category === "CUSTOMER_EQUIPMENT"
  const assigned = state !== "AVAILABLE"
  function changeSite(value: string) {
    setSite(value)
    setService("")
    if (mode === "SERVICE") setMode("NONE")
  }
  return <>
    <div className="form-grid crm-relations">
      <Select name="assignment_state" label="Situación del equipo" value={state} onChange={(event) => {
        setState(event.target.value)
        if (event.target.value === "AVAILABLE" && mode === "SERVICE") setMode("NONE")
      }}>
        {assignmentStates.filter(([value]) => value !== "RETIRED" && (!startAssigned || value !== "AVAILABLE"))
          .map(([value, label]) => <option value={value} key={value}>{label}</option>)}
      </Select>
      {assigned && <>
        {clientId && <input type="hidden" name="client_id" value={clientId} />}
        {siteId && <input type="hidden" name="site_id" value={siteId} />}
        {finalEquipment && !clientId && !siteId && <Relation kind="clients" label="Cliente" name="client_id" value={client}
          known={asText(entry, "client_name")} account={account} required filters={{ status: "ACTIVE" }}
          change={(value) => { setClient(value); changeSite("") }} />}
        {!siteId && (!finalEquipment || client) && <Relation key={category + client} kind="sites" label="Sitio" name="site_id"
          value={site} known={asText(entry, "site_name")} account={account} required
          filters={finalEquipment ? { status: "ACTIVE", client_id: client } : { status: "ACTIVE", isp_site: "true" }}
          change={changeSite} />}
        {finalEquipment && site && <Relation key={site} kind="services" label="Servicio asociado" name="service_id" value={service}
          known={asText(entry, "service_plan_name")} account={account} filters={{ site_id: site, linkable_service: "true" }}
          change={(id) => { setService(id); if (!id && mode === "SERVICE") setMode("NONE") }} />}
      </>}
      <Select name="ip_mode" label="Origen de la IP de gestión" value={mode} onChange={(event) => setMode(event.target.value)}>
        {ipModes.filter(([value]) => value !== "SERVICE" || (assigned && !!service))
          .map(([value, label]) => <option value={value} key={value}>{label}</option>)}
      </Select>
      {mode === "INDEPENDENT" && <Field name="ip_address" label="IPv4 de gestión" required defaultValue={asText(entry, "ip_address_text")} />}
    </div>
    {mode === "SERVICE" && <p className="description">El destino seguirá la IP registrada en el servicio.</p>}
  </>
}

export function AssignAvailable({ account, clientId, siteId, category, complete, cancel }: {
  account: Account; clientId?: string; siteId?: string; category: string; complete: () => void; cancel: () => void
}) {
  const [device, setDevice] = useState("")
  return <Panel title="Asignar equipo disponible"><div className="panel-body">
    <ActionForm label="Asignar equipo" cancel={cancel} submit={async (form) => {
      await api("isp", `${crm}/devices/${device}/assignment`, "POST", { ...placementInput(form), reason: textValue(form, "reason") })
      complete()
    }}>
      <Relation kind="devices" name="device_id" label="Equipo disponible" required value={device} account={account}
        filters={{ assignment_state: "AVAILABLE", device_category: category, status: "ACTIVE" }} change={setDevice} />
      <PlacementFields account={account} category={category} clientId={clientId} siteId={siteId} startAssigned />
      <Field label="Motivo" name="reason" minLength={2} maxLength={500} required defaultValue="Asignación operativa" />
    </ActionForm>
  </div></Panel>
}

export function AssignmentHistory({ id }: { id: string }) {
  const pager = usePager()
  type Change = { id: string; occurred_at: string; actor: string; reason: string | null;
    previous_data: Record<string, string> | null; current_data: Record<string, string> }
  const state = useData<Page<Change>>("isp", searchPath(`${crm}/devices/${id}/assignments`, pager.offset))
  return <Panel title="Historial de asignaciones"><DataView state={state}>{({ items, has_more }) => <>
    <DataTable headers={["Fecha", "Operador", "Anterior", "Nuevo", "Origen de IP", "Motivo"]}
      empty={items.length ? undefined : "No hay cambios de asignación registrados."}>
      {items.map((item) => <tr key={item.id}><td>{dateText(item.occurred_at)}</td><td>{item.actor}</td>
        <td>{optionsLabel(assignmentStates, item.previous_data?.assignment_state)}</td>
        <td>{optionsLabel(assignmentStates, item.current_data.assignment_state)}</td>
        <td>{optionsLabel(ipModes, item.current_data.ip_mode)}</td><td>{item.reason || "—"}</td>
      </tr>)}
    </DataTable><Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
  </>}</DataView></Panel>
}
