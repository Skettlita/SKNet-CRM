import type { ReactNode } from "react"
import { useState } from "react"

import { Field } from "../auth/forms"
import type { Account } from "../auth/api"
import { Select, TextArea, amountText, dateText, integerValue, optionalValue, textValue, useData } from "../platform/shared"
import type { Page } from "../platform/shared"

export type Kind = "clients" | "internet-plans" | "services" | "sites" | "devices"
export type Entry = { id: string; [key: string]: string | number | boolean | null | undefined }
type Column = [label: string, value: (row: Entry) => ReactNode]
type Option = [value: string, label: string]
type FieldSpec = { key: string; label: string; type?: string; required?: boolean; options?: Option[]; max?: number; min?: number; step?: string }
type CatalogSpec = {
  title: string; singular: string; permission: string; categories: Option[]; categoryLabel?: string
  columns: Column[]; fields: FieldSpec[]
}

export const crm = "/crm"
export const appPath = (kind: Kind, id = "") => `/app/${kind}${id ? "/" + id : ""}`
export const asText = (row: Entry | undefined, key: string) => String(row?.[key] ?? "")
export const titleOf = (kind: Kind, row: Entry) => kind === "services"
  ? [asText(row, "client_name"), asText(row, "plan_name")].filter(Boolean).join(" · ")
  : asText(row, "name")
export const allowed = (account: Account, permission: string) => account.permissions.includes(permission)

export const personTypes: Option[] = [["PERSON", "Persona natural"], ["COMPANY", "Empresa"]]
export const siteTypes: Option[] = [
  ["CLIENT_SITE", "Sitio de cliente"], ["NODE", "Nodo"], ["TOWER", "Torre"], ["OFFICE", "Oficina"],
  ["WAREHOUSE", "Almacén"], ["WORKSHOP", "Taller"], ["OTHER", "Otro"],
]
export const roles: Option[] = [["NODE", "Nodo o equipo principal"], ["INTERMEDIATE", "Equipo intermedio"], ["ENDPOINT", "Dispositivo final"]]
const access: Option[] = [["PPPOE", "PPPoE"], ["DHCP", "DHCP"], ["STATIC", "IP estática"], ["OTHER", "Otro"]]
const assignments: Option[] = [["DYNAMIC", "Dinámica"], ["FIXED", "Fija"]]
export const serviceStates: Option[] = [["PENDING", "Pendiente"], ["ACTIVE", "Activo"], ["SUSPENDED", "Suspendido"], ["CANCELLED", "Cancelado"]]
export const optionsLabel = (options: Option[], value: unknown) => options.find(([id]) => id === value)?.[1] ?? String(value ?? "—")
const string = (key: string) => (row: Entry) => asText(row, key) || "—"
const choice = (key: string, values: Option[]) => (row: Entry) => optionsLabel(values, row[key])
const amount = (row: Entry) => amountText(asText(row, "monthly_price"), asText(row, "currency"))
const field = (key: string, label: string, options: Omit<FieldSpec, "key" | "label"> = {}): FieldSpec => ({ key, label, ...options })
const name = (label: string) => field("name", label, { required: true })
const commonNotes = field("observations", "Observaciones", { type: "textarea" })
const description = field("description", "Descripción", { type: "textarea" })

export const catalogs: Record<Kind, CatalogSpec> = {
  clients: {
    title: "Clientes", singular: "cliente", permission: "clients", categories: personTypes, categoryLabel: "Tipo de cliente",
    columns: [["Código", string("client_code")], ["Tipo", choice("client_type", personTypes)],
      ["Documento", string("document_number")], ["Teléfono", string("phone")], ["Correo", string("email")]],
    fields: [name("Nombre o razón social"), field("client_code", "Código de cliente", { required: true }),
      field("client_type", "Tipo de cliente", { options: personTypes, required: true }),
      field("document_type", "Tipo de documento"), field("document_number", "Número de documento o NIT"),
      field("phone", "Teléfono", { type: "tel", max: 30 }), field("email", "Correo", { type: "email", max: 254 }), commonNotes],
  },
  "internet-plans": {
    title: "Planes de Internet", singular: "plan de Internet", permission: "internet_plans", categories: [],
    columns: [["Tipo", string("service_type")], ["Descarga (Mbps)", string("download_mbps")],
      ["Subida (Mbps)", string("upload_mbps")], ["Precio mensual", amount]],
    fields: [name("Nombre del plan"), field("service_type", "Tipo de servicio", { required: true }),
      field("download_mbps", "Descarga (Mbps)", { type: "number", min: 1 }), field("upload_mbps", "Subida (Mbps)", { type: "number", min: 1 }),
      field("monthly_price", "Precio mensual", { type: "number", min: 0, step: "0.01", required: true }),
      field("currency", "Moneda", { max: 3, required: true }), description, commonNotes],
  },
  services: {
    title: "Servicios contratados", singular: "servicio", permission: "services", categories: access, categoryLabel: "Modalidad de acceso",
    columns: [["Sitio", string("site_name")], ["Acceso", choice("access_method", access)], ["IP del servicio", string("service_ip_text")],
      ["Precio contratado", amount], ["Activación", (row) => dateText(asText(row, "activated_at"))]],
    fields: [field("contracted_on", "Fecha de contratación", { type: "date" }),
      field("monthly_price", "Precio contratado", { type: "number", min: 0, step: "0.01" }), field("currency", "Moneda", { max: 3 }),
      field("access_method", "Modalidad de acceso", { options: access, required: true }),
      field("ip_assignment", "Asignación de IP", { options: assignments }),
      field("pppoe_username", "Usuario PPPoE"), field("service_ip", "Dirección IP del servicio"),
      field("access_mac", "MAC de acceso", { max: 17 }), field("technical_notes", "Observaciones técnicas", { type: "textarea" }), commonNotes],
  },
  sites: {
    title: "Sitios", singular: "sitio", permission: "sites", categories: siteTypes, categoryLabel: "Tipo de sitio",
    columns: [["Tipo", choice("site_type", siteTypes)], ["Cliente", string("client_name")], ["Ciudad", string("city")], ["Dirección", string("address")]],
    fields: [name("Nombre del sitio"), field("site_type", "Tipo de sitio", { options: siteTypes, required: true }),
      field("address", "Dirección", { max: 400 }), field("city", "Ciudad"),
      field("latitude", "Latitud", { type: "number", min: -90, max: 90, step: "0.000001" }),
      field("longitude", "Longitud", { type: "number", min: -180, max: 180, step: "0.000001" }), description],
  },
  devices: {
    title: "Dispositivos", singular: "dispositivo", permission: "devices", categories: roles, categoryLabel: "Rol en la red",
    columns: [["IP de gestión", string("ip_address_text")], ["Fabricante", string("brand")], ["Modelo", string("model")],
      ["Tipo", string("device_type")], ["Rol", choice("device_role", roles)], ["Sitio", string("site_name")]],
    fields: [name("Nombre del dispositivo"), field("ip_address", "Dirección IPv4 de gestión"),
      field("brand", "Fabricante"), field("model", "Modelo"), field("device_type", "Tipo de dispositivo", { required: true }),
      field("device_role", "Rol en la red", { options: roles, required: true }), description],
  },
}

export function administrativeStatus(kind: Kind, row: Entry) {
  return kind === "devices" ? row.administrative_active && !row.retired_at ? "ACTIVE" : "INACTIVE"
    : kind === "sites" || kind === "internet-plans" ? row.active ? "ACTIVE" : "INACTIVE" : asText(row, "status")
}

export function valueFor(row: Entry | undefined, key: string) {
  if (key === "ip_address" || key === "service_ip") return asText(row, key + "_text")
  return asText(row, key)
}

export function Fields({ fields, row, onChange, values = {} }: {
  fields: FieldSpec[]; row?: Entry; onChange?: (key: string, value: string) => void; values?: Record<string, string>
}) {
  return <div className="form-grid">
    {fields.map(({ key, label, type, required, options, max, min, step }) => {
      const initial = valueFor(row, key) || (key === "currency" && required ? "BOB" : key === "service_type" ? "INTERNET" : "")
      if (type === "textarea") return <TextArea key={key} label={label} name={key} defaultValue={initial} maxLength={max ?? 4000} />
      if (options) return <Select key={key} label={label} name={key} required={required}
        {...(key in values ? { value: values[key] } : { defaultValue: initial })}
        onChange={(event) => onChange?.(key, event.target.value)}>
        <option value="">{required ? "Selecciona…" : "Sin definir"}</option>
        {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </Select>
      return <Field key={key} label={label} name={key} type={type} defaultValue={initial} required={required}
        min={min} max={type === "number" ? max : undefined} step={step}
        maxLength={type === "number" ? undefined : max ?? 120} />
    })}
  </div>
}

export function payload(spec: FieldSpec[], fields: FormData) {
  return Object.fromEntries(spec.map(({ key, required }) => [
    key, ["download_mbps", "upload_mbps"].includes(key) ? integerValue(fields, key) :
      required ? textValue(fields, key) : optionalValue(fields, key),
  ]))
}

export function Relation({ kind, name, label, value, known, account, required, filters, change }: {
  kind: Kind; name: string; label: string; value: string; known?: string; account: Account
  required?: boolean; filters?: Record<string, string>; change: (id: string) => void
}) {
  const [query, setQuery] = useState("")
  const [selectedName, setSelectedName] = useState(known)
  const canRead = allowed(account, catalogs[kind].permission + ".read")
  const params = new URLSearchParams({ q: query, limit: "60", ...filters })
  const result = useData<Page<Entry>>("isp", canRead ? `${crm}/${kind}?${params}` : null)
  const entries = result.data?.items ?? []
  const hasValue = entries.some((item) => item.id === value)
  return <div className="relation-control">
    {canRead && <Field label={"Buscar " + label.toLowerCase()} type="search" maxLength={120}
      value={query} onChange={(event) => setQuery(event.target.value)} />}
    <Select label={label} name={name} required={required} value={value} onChange={(event) => {
      const option = entries.find((item) => item.id === event.target.value)
      setSelectedName(option && titleOf(kind, option))
      change(event.target.value)
    }}>
      <option value="">{required ? "Selecciona…" : "Sin asociar"}</option>
      {value && !hasValue && <option value={value}>{selectedName || known || "Registro asociado"}</option>}
      {entries.map((item) => <option value={item.id} key={item.id}>{titleOf(kind, item)}</option>)}
    </Select>
    {result.error && <p className="form-error" role="alert">{result.error}</p>}
    {!canRead && !value && <p className="description">Falta el permiso para consultar {catalogs[kind].title.toLowerCase()}.</p>}
    {result.data?.has_more && <p className="description">Afina la búsqueda para ver más opciones.</p>}
  </div>
}
