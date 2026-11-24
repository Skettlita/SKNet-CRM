import type { ReactNode } from "react"
import { useState } from "react"

import { Field } from "../auth/forms"
import type { Account } from "../auth/api"
import { Select, TextArea, amountText, dateText, integerValue, optionalValue, textValue, useData } from "../platform/shared"
import type { Page } from "../platform/shared"

export type Kind = "clients" | "internet-plans" | "services" | "sites" | "devices"
export type Entry = { id: string; [key: string]: string | number | boolean | string[] | null | undefined }
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
export const siteCategories: Option[] = [
  ["CUSTOMER", "Sitios de clientes"], ["NETWORK", "Infraestructura de red"], ["FACILITY", "Instalaciones propias"],
]
export const siteTypesByCategory: Record<string, Option[]> = {
  CUSTOMER: [["HOME", "Domicilio"], ["CLIENT_OFFICE", "Oficina"], ["BRANCH", "Sucursal"], ["BUILDING", "Edificio"],
    ["BUSINESS_INSTALLATION", "Instalación empresarial"], ["CUSTOMER_OTHER", "Otro"]],
  NETWORK: [["MAIN_NODE", "Nodo principal"], ["DISTRIBUTION_NODE", "Nodo de distribución"], ["TOWER", "Torre"],
    ["BASE_STATION", "Estación base"], ["DATA_CENTER", "Centro de datos"], ["ACCESS_POINT", "Punto de acceso"], ["NETWORK_OTHER", "Otro"]],
  FACILITY: [["ADMIN_OFFICE", "Oficina administrativa"], ["WAREHOUSE", "Almacén"], ["WORKSHOP", "Taller"],
    ["OPERATIONS_CENTER", "Centro de operaciones"], ["FACILITY_OTHER", "Otro"]],
}
export const siteTypes = Object.values(siteTypesByCategory).flat()
export const deviceCategories: Option[] = [["INFRASTRUCTURE", "Infraestructura"], ["CUSTOMER_EQUIPMENT", "Equipo final"]]
export const capabilities: Option[] = [["PPPOE_SERVER", "Servidor PPPoE"], ["DHCP_SERVER", "Servidor DHCP"],
  ["ACCESS_ROUTER", "Router de acceso"], ["DISTRIBUTION", "Distribución de red"]]
export const installationSituations: Option[] = [["NEW", "Requiere una nueva instalación"],
  ["EXISTING", "Servicio existente, previamente instalado"], ["UNDEFINED", "Instalación pendiente de definir"]]
export const codeFields: Partial<Record<Kind, string>> = {
  clients: "client_code", sites: "site_code", services: "service_code", devices: "device_code",
}
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
    fields: [name("Nombres y apellidos o razón social"),
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
    columns: [["Código", string("service_code")], ["Sitio", string("site_name")], ["Acceso", choice("access_method", access)], ["IP del servicio", string("service_ip_text")],
      ["Precio contratado", amount], ["Activación", (row) => dateText(asText(row, "activated_at"))]],
    fields: [field("contracted_on", "Fecha de contratación", { type: "date" }),
      field("monthly_price", "Precio contratado", { type: "number", min: 0, step: "0.01" }), field("currency", "Moneda", { max: 3 }),
      field("access_method", "Modalidad de acceso", { options: access, required: true }),
      field("ip_assignment", "Asignación de IP", { options: assignments }),
      field("pppoe_username", "Usuario PPPoE"), field("service_ip", "Dirección IP del servicio"),
      field("access_mac", "MAC de acceso", { max: 17 }), field("technical_notes", "Observaciones técnicas", { type: "textarea" }), commonNotes],
  },
  sites: {
    title: "Sitios", singular: "sitio", permission: "sites", categories: [],
    columns: [["Código", string("site_code")], ["Categoría", choice("site_category", siteCategories)], ["Tipo", choice("site_type", siteTypes)],
      ["Cliente", string("client_name")], ["Ciudad", string("effective_city")], ["Dirección", string("effective_address")]],
    fields: [name("Nombre del sitio"), field("site_type", "Tipo de sitio", { options: siteTypes, required: true }),
      field("address", "Dirección", { max: 400 }), field("city", "Ciudad"),
      field("latitude", "Latitud", { type: "number", min: -90, max: 90, step: "0.000001" }),
      field("longitude", "Longitud", { type: "number", min: -180, max: 180, step: "0.000001" }), description],
  },
  devices: {
    title: "Dispositivos", singular: "dispositivo", permission: "devices", categories: roles, categoryLabel: "Rol en la red",
    columns: [["Código", string("device_code")], ["Categoría", choice("device_category", deviceCategories)],
      ["IP de gestión", string("ip_address_text")], ["Fabricante", string("brand")], ["Modelo", string("model")],
      ["Tipo", string("device_type")], ["Rol", choice("device_role", roles)], ["Sitio", string("site_name")]],
    fields: [name("Nombre del dispositivo"), field("ip_address", "Dirección IPv4 de gestión"),
      field("brand", "Fabricante"), field("model", "Modelo"), field("device_type", "Tipo de dispositivo", { required: true }),
      field("serial_number", "Número de serie"), field("mac_address", "MAC del dispositivo", { max: 17 }),
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

export function Fields({ fields, row, onChange, values = {}, prefix = "" }: {
  fields: FieldSpec[]; row?: Entry; onChange?: (key: string, value: string) => void; values?: Record<string, string>; prefix?: string
}) {
  return <div className="form-grid">
    {fields.map(({ key, label, type, required, options, max, min, step }) => {
      const initial = valueFor(row, key) || (key === "currency" && required ? "BOB" : key === "service_type" ? "INTERNET" : "")
      const inputName = prefix + key
      if (type === "textarea") return <TextArea key={key} label={label} name={inputName} defaultValue={initial} maxLength={max ?? 4000} />
      if (options) return <Select key={key} label={label} name={inputName} required={required}
        {...(key in values ? { value: values[key] } : { defaultValue: initial })}
        onChange={(event) => onChange?.(key, event.target.value)}>
        <option value="">{required ? "Selecciona…" : "Sin definir"}</option>
        {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </Select>
      return <Field key={key} label={label} name={inputName} type={type} required={required}
        {...(key in values ? { value: values[key] } : { defaultValue: initial })}
        onChange={(event) => onChange?.(key, event.target.value)}
        min={min} max={type === "number" ? max : undefined} step={step}
        maxLength={type === "number" ? undefined : max ?? 120} />
    })}
  </div>
}

export function payload(spec: FieldSpec[], fields: FormData, prefix = "") {
  return Object.fromEntries(spec.map(({ key, required }) => [
    key, ["download_mbps", "upload_mbps"].includes(key) ? integerValue(fields, prefix + key) :
      required ? textValue(fields, prefix + key) : optionalValue(fields, prefix + key),
  ]))
}

export function Relation({ kind, name, label, value, known, account, required, filters, change }: {
  kind: Kind; name: string; label: string; value: string; known?: string; account: Account
  required?: boolean; filters?: Record<string, string>; change: (id: string, record?: Entry) => void
}) {
  const [query, setQuery] = useState("")
  const [selectedName, setSelectedName] = useState(known)
  const canRead = allowed(account, catalogs[kind].permission + ".read")
  const params = new URLSearchParams({ q: query, limit: "60", ...filters })
  const result = useData<Page<Entry>>("isp", canRead ? `${crm}/${kind}?${params}` : null)
  const entries = result.data?.items ?? []
  const codeField = codeFields[kind]
  const hasValue = entries.some((item) => item.id === value)
  return <div className="relation-control">
    {canRead && <Field label={"Buscar " + label.toLowerCase()} type="search" maxLength={120}
      value={query} onChange={(event) => setQuery(event.target.value)} />}
    <Select label={label} name={name} required={required} value={value} onChange={(event) => {
      const option = entries.find((item) => item.id === event.target.value)
      setSelectedName(option && titleOf(kind, option))
      change(event.target.value, option)
    }}>
      <option value="">{required ? "Selecciona…" : "Sin asociar"}</option>
      {value && !hasValue && <option value={value}>{selectedName || known || "Registro asociado"}</option>}
      {entries.map((item) => <option value={item.id} key={item.id}>
        {titleOf(kind, item)}{codeField && item[codeField] ? " · " + item[codeField] : ""}
      </option>)}
    </Select>
    {result.error && <p className="form-error" role="alert">{result.error}</p>}
    {!canRead && !value && <p className="description">Falta el permiso para consultar {catalogs[kind].title.toLowerCase()}.</p>}
    {result.data?.has_more && <p className="description">Afina la búsqueda para ver más opciones.</p>}
  </div>
}
