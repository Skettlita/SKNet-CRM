import { useEffect, useState } from "react"
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react"

import { api, message } from "../auth/api"
import type { Scope } from "../auth/api"
import { Button } from "../shared/Button"

export type Page<T> = { items: T[]; has_more: boolean }
export const PAGE_SIZE = 25

export function useData<T>(scope: Scope, path: string | null, version = 0) {
  const [state, setState] = useState<{ data?: T; error?: string; path?: string | null }>({})
  useEffect(() => {
    if (!path) return
    let current = true
    api<T>(scope, path).then((data) => {
      if (current) setState({ path, data })
    }).catch((error) => {
      if (current) setState({ path, error: message(error) })
    })
    return () => { current = false }
  }, [scope, path, version])
  return state.path === path ? state : {}
}

export function usePager() {
  const [offset, setOffset] = useState(0)
  const [version, setVersion] = useState(0)
  return { offset, setOffset, version, reload: () => setVersion((value) => value + 1) }
}

export function searchPath(path: string, offset: number, filters: Record<string, string> = {}) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(PAGE_SIZE) })
  for (const [name, value] of Object.entries(filters)) if (value) params.set(name, value)
  return `${path}?${params}`
}

export function Panel({ title, children }: { title?: string; children: ReactNode }) {
  return <section className="table-panel platform-panel">
    {title && <div className="panel-header"><h2>{title}</h2></div>}
    {children}
  </section>
}

export function DataView<T>({ state, children }: {
  state: { data?: T; error?: string }; children: (data: T) => ReactNode
}) {
  if (state.error) return <p className="panel-message form-error" role="alert">{state.error}</p>
  if (state.data === undefined) return <p className="panel-message" role="status">Cargando…</p>
  return children(state.data)
}

export function DataTable({ headers, children, empty }: {
  headers: string[]; children: ReactNode; empty?: string
}) {
  if (empty) return <p className="panel-message">{empty}</p>
  return <div className="table-scroll">
    <table className="device-table access-table">
      <thead><tr>{headers.map((header) => <th scope="col" key={header}>{header}</th>)}</tr></thead>
      <tbody>{children}</tbody>
    </table>
  </div>
}

export function Pagination({ offset, more, onChange }: {
  offset: number; more: boolean; onChange: (offset: number) => void
}) {
  return offset > 0 || more ? <div className="table-controls pagination-controls">
    <Button disabled={offset === 0} onClick={() => onChange(offset - PAGE_SIZE)}>Anterior</Button>
    <span>Página {offset / PAGE_SIZE + 1}</span>
    <Button disabled={!more} onClick={() => onChange(offset + PAGE_SIZE)}>Siguiente</Button>
  </div> : null
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { label: string }
export function Select({ label, children, ...props }: SelectProps) {
  return <label className="form-field"><span>{label}</span><select {...props}>{children}</select></label>
}

export function TextArea({ label, ...props }: {
  label: string; name: string; defaultValue?: string; required?: boolean; minLength?: number; maxLength?: number
}) {
  return <label className="form-field"><span>{label}</span><textarea rows={3} {...props} /></label>
}

export function Search({ label, ...input }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return <label className="form-field"><span>{label}</span><input type="search" maxLength={120} {...input} /></label>
}

const statusNames: Record<string, string> = {
  ACTIVE: "Activa", INACTIVE: "Suspendida", CLOSED: "Cerrada", TRIAL: "Prueba", GRACE: "En gracia",
  PENDING: "Pendiente", SUSPENDED: "Suspendida", CANCELLED: "Cancelada", UNCONFIGURED: "Sin configurar", UNKNOWN: "Sin datos",
  CONNECTED: "Conectada", DISCONNECTED: "Desconectada", STALE: "Sin datos recientes",
  DISABLED: "Deshabilitada", ENABLED: "Habilitado", PLAN_OFF: "Desactivado",
  OPEN: "Abierto", ASSIGNED: "Asignado", IN_PROGRESS: "En curso", RESOLVED: "Resuelto",
  LOW: "Baja", NORMAL: "Normal", HIGH: "Alta", CRITICAL: "Crítica",
  PROVISIONING: "Aprovisionando", WAITING_PUBLIC_KEY: "Esperando clave pública",
  WAITING_HANDSHAKE: "Esperando conectividad", READY: "Operativo", ERROR: "Error",
  RUNNING: "En ejecución", EXITED: "Detenido", MISSING: "Sin contenedor", CREATED: "Creado",
  SUCCEEDED: "Completado", FAILED: "Fallido", SIMULATED: "Simulación",
}
export const statusName = (value: string) => statusNames[value] ?? value

export function Status({ value }: { value: string }) {
  const tone = ["ACTIVE", "CONNECTED", "ENABLED", "RESOLVED", "RUNNING", "READY", "SUCCEEDED"].includes(value) ? "up"
    : ["INACTIVE", "SUSPENDED", "DISCONNECTED", "CRITICAL", "ERROR", "FAILED"].includes(value) ? "down"
    : ["TRIAL", "GRACE", "STALE", "HIGH", "SIMULATED"].includes(value) ? "warn" : "muted"
  return <span className={`status status-${tone}`}><i aria-hidden="true" />{statusName(value)}</span>
}

export const dateText = (value: string | null | undefined) => value
  ? new Date(value).toLocaleString("es-BO", { dateStyle: "short", timeStyle: "short" }) : "—"

export const amountText = (value: number | string, currency: string) =>
  new Intl.NumberFormat("es-BO", { style: "currency", currency }).format(Number(value))

export const textValue = (fields: FormData, name: string) => String(fields.get(name) ?? "").trim()
export const optionalValue = (fields: FormData, name: string) => textValue(fields, name) || null
export const integerValue = (fields: FormData, name: string) => {
  const value = optionalValue(fields, name)
  return value === null ? null : Number(value)
}

export type Choice = { id: string; name: string }
export type PlanChoice = Choice & { version_id: string; version: number; code: string; latest: boolean }
export type Usage = { clients: number; users: number; monitored_devices: number }

export type Subscription = {
  id: string; company_id: string; company_name: string; plan_version_id: string; plan_code: string
  plan_name: string; plan_version: number; status: string; starts_at: string; ends_at: string | null
  max_clients: number | null; max_users: number | null; max_devices: number | null
  min_poll_interval_seconds: number | null; retention_days: number | null; current: boolean
  price: number | string; currency: string; billing_period: string
}

export function ResourceUsage({ usage, subscription }: { usage: Usage; subscription: Subscription | null }) {
  const entries = [
    ["Clientes", usage.clients, subscription?.max_clients],
    ["Usuarios activos", usage.users, subscription?.max_users],
    ["Dispositivos con monitoreo solicitado o habilitado", usage.monitored_devices, subscription?.max_devices],
  ] as const
  return <DataTable headers={["Recurso", "Utilizados", "Límite"]}>
    {entries.map(([name, count, limit]) => <tr key={name}>
      <td>{name}</td><td className={limit != null && count > limit ? "form-error" : undefined}>{count}</td>
      <td>{subscription === null ? "—" : limit ?? "Sin límite"}</td>
    </tr>)}
  </DataTable>
}
