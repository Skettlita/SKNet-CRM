import { useState } from "react"
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { PageHeading } from "../auth/AccessManagement"
import type { Account } from "../auth/api"
import { DataTable, DataView, Panel, Pagination, Search, Select, Status, dateText, searchPath, useData, usePager } from "../platform/shared"
import type { Page } from "../platform/shared"
import { Relation, allowed, appPath, asText, deviceCategories, optionsLabel, roles, useOptions } from "./model"
import type { Entry } from "./model"

const endpoint = "/monitoring"
const states = ["UP", "DEGRADED", "DOWN", "UNREACHABLE", "STALE", "UNKNOWN", "UNCONFIGURED", "DISABLED"]
const labels: Record<string, string> = { UP: "Disponible", DEGRADED: "Degradado", DOWN: "Caído", UNREACHABLE: "Inalcanzable",
  STALE: "Datos vencidos", UNKNOWN: "Sin datos", UNCONFIGURED: "Sin configurar", DISABLED: "Deshabilitado" }
const incidentLabels: Record<string, string> = { VPN: "VPN", COLLECTOR: "Collector", ICMP_UNREACHABLE: "ICMP" }
const eligibility: Record<string, string> = {
  NOT_INSTALLED: "Equipo sin instalar", NO_ADDRESS: "Sin IPv4 de gestión",
  UNAUTHORIZED_NETWORK: "Red fuera de las rutas autorizadas", COLLECTOR_UNAVAILABLE: "Collector no disponible",
  DUPLICATE: "Destino ya solicitado por otro equipo",
}
type MonitorPage = Page<Entry> & { monitored: number; states: Record<string, number> }
type Sample = { checked_at: string; ip: string | null; result: string; packets_sent: number | null; packets_received: number | null
  latency_ms: number | null; packet_loss_pct: number | null; transport_healthy: boolean; error_detail: string | null }
type Point = Record<"latency" | "loss" | "availability", number | null> & { bucket: string; valid_samples: number }
type Incident = {
  id: string; device_id: string | null; name: string; kind: string; client_name: string | null; site_name: string | null
  device_category: string | null; started_at: string; ended_at: string | null; duration_seconds: number; summary: string | null
}
type Detail = {
  status: string; effective_ip: string | null; ip_mode: string; collector_name: string | null; last_latency_ms: number | null
  last_packet_loss_pct: number | null; last_check_at: string | null; last_success_at: string | null
  eligibility_reason: string | null
  samples: Sample[]; series: Point[]; incidents: Incident[]
}

function measure(value: number | string | boolean | string[] | null | undefined, unit: string) {
  return value == null ? "—" : `${value} ${unit}`
}
function duration(value?: number | null) {
  if (value == null) return "—"
  const mins = Math.floor(value/60)
  return mins >= 60 ? `${Math.floor(mins/60)} h ${mins%60} min` : mins ? `${mins} min` : `${value} s`
}

export function MonitoringList({ account }: { account: Account }) {
  const pager = usePager()
  const [filters, setFilters] = useState<Record<string, string>>({})
  const change = (key: string, value: string) => { setFilters((old) => ({ ...old, [key]: value })); pager.setOffset(0) }
  const state = useData<MonitorPage>("isp", searchPath(endpoint + "/devices", pager.offset, filters), 0, 5000)
  const types = useOptions<{ id: string; name: string }>(endpoint + "/device-types")
  return <><PageHeading title="Monitoreo ICMP" />
    <div className="crm-tabs" aria-label="Categoría de los equipos">
      {[["", "Todos los equipos"], ...deviceCategories].map(([value, label]) => <button key={value} type="button"
        aria-pressed={(filters.category || "") === value} onClick={() => change("category", value)}>{label}</button>)}
    </div>
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar nombre, código, cliente, sitio o IP" value={filters.q ?? ""} onChange={(e) => change("q", e.target.value)} />
        <Select label="Estado técnico" value={filters.status ?? ""} onChange={(e) => change("status", e.target.value)}>
          <option value="">Todos</option>{states.map((item) => <option key={item} value={item}>{labels[item]}</option>)}
        </Select>
        <Select label="Rol topológico" value={filters.role ?? ""} onChange={(e) => change("role", e.target.value)}>
          <option value="">Todos</option>{roles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        <Select label="Tipo de dispositivo" value={filters.type_id ?? ""} onChange={(e) => change("type_id", e.target.value)}>
          <option value="">Todos</option>{types.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>
      </div>
      <div className="table-controls platform-filters">
        {allowed(account, "clients.read") && <Relation kind="clients" name="client_filter" label="Cliente" value={filters.client_id ?? ""}
          account={account} change={(value) => { change("client_id", value); change("site_id", "") }} />}
        {allowed(account, "sites.read") && <Relation kind="sites" name="site_filter" label="Sitio" value={filters.site_id ?? ""}
          account={account} filters={filters.client_id ? { client_id: filters.client_id } : {}} change={(value) => change("site_id", value)} />}
      </div>
      <DataView state={state}>{(data) => <>
        <div className="table-controls"><strong>{data.monitored} monitoreados</strong>
          {states.map((status) => <span key={status}>{labels[status]} · {data.states[status] ?? 0}</span>)}
        </div>
        <DataTable headers={["Dispositivo", "Código", "Categoría", "Cliente", "Sitio", "IP efectiva", "Estado", "RTT medio", "Pérdida", "Última prueba", "Duración"]}
          empty={!data.items.length ? "No hay dispositivos que coincidan." : undefined}>
          {data.items.map((device) => <tr key={device.id}>
            <td>{allowed(account, "devices.read") ? <a className="platform-link" href={appPath("devices", device.id) + "?tab=monitoring"}>{device.name}</a> : device.name}</td>
            <td>{device.device_code}</td><td>{optionsLabel(deviceCategories, device.device_category)}</td><td>{device.client_name || "—"}</td>
            <td>{device.site_name || "—"}</td><td>{device.effective_ip || "—"}</td><td><Status value={asText(device, "status")} />
              {device.eligibility_reason && <small className="relation-secondary">{eligibility[asText(device, "eligibility_reason")]}</small>}</td>
            <td>{measure(device.last_latency_ms, "ms")}</td><td>{measure(device.last_packet_loss_pct, "%")}</td>
            <td>{dateText(asText(device, "last_check_at"))}</td><td>{duration(typeof device.duration_seconds === "number" ? device.duration_seconds : null)}</td>
          </tr>)}
        </DataTable>
        <Pagination offset={pager.offset} more={data.has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

function IncidentTable({ items, links }: { items: Incident[]; links: boolean }) {
  return <DataTable headers={["Equipo o transporte", "Origen", "Cliente / Sitio", "Inicio", "Fin", "Duración", "Diagnóstico"]}
    empty={!items.length ? "No se registraron incidentes." : undefined}>
    {items.map((item) => <tr key={item.id}>
      <td>{links && item.device_id ? <a className="platform-link" href={appPath("devices", item.device_id) + "?tab=monitoring"}>{item.name}</a> : item.name}</td>
      <td>{item.device_category ? optionsLabel(deviceCategories, item.device_category) : incidentLabels[item.kind] || item.kind}</td>
      <td>{[item.client_name, item.site_name].filter(Boolean).join(" · ") || "—"}</td><td>{dateText(item.started_at)}</td>
      <td>{item.ended_at ? dateText(item.ended_at) : "Activo"}</td><td>{duration(item.duration_seconds)}</td><td>{item.summary || "—"}</td>
    </tr>)}
  </DataTable>
}

export function IncidentsPage({ account }: { account: Account }) {
  const pager = usePager()
  const [q, setQ] = useState("")
  const [kind, setKind] = useState("")
  const [active, setActive] = useState("")
  const state = useData<Page<Incident>>("isp", searchPath(endpoint + "/incidents", pager.offset, { q, kind, active }), 0, 5000)
  return <><PageHeading title="Incidentes" /><Panel>
    <div className="table-controls platform-filters">
      <Search label="Buscar incidentes" value={q} onChange={(e) => { setQ(e.target.value); pager.setOffset(0) }} />
      <Select label="Origen" value={kind} onChange={(e) => { setKind(e.target.value); pager.setOffset(0) }}>
        <option value="">Todos</option>{[...deviceCategories, ["VPN", "VPN"], ["COLLECTOR", "Collector"]].map(([value, label]) =>
          <option key={value} value={value}>{label}</option>)}
      </Select>
      <Select label="Estado" value={active} onChange={(e) => { setActive(e.target.value); pager.setOffset(0) }}>
        <option value="">Todos</option><option value="true">Activos</option><option value="false">Cerrados</option>
      </Select>
    </div>
    <DataView state={state}>{({ items, has_more }) => <>
      <IncidentTable items={items} links={allowed(account, "devices.read")} />
      <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
    </>}</DataView>
  </Panel></>
}

const charts = [["latency", "Latencia (ms)"], ["loss", "Pérdida (%)"], ["availability", "Comprobaciones aceptables (%)"]] as const
const results: Record<string, string> = { REACHABLE: "Respondió", NO_REPLY: "Sin respuesta", ERROR: "Error técnico", SKIPPED_VPN: "VPN sin visibilidad" }

export function MonitoringDetail({ id }: { id: string }) {
  const [period, setPeriod] = useState("24h")
  const state = useData<Detail>("isp", endpoint + "/devices/" + id + "?period=" + period, 0, 5000)
  const ticks = new Intl.DateTimeFormat("es-BO", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
  return <DataView state={state}>{(info) => <>
    <Panel title="Mediciones e históricos"><div className="panel-body">
      <div className="form-grid">
        <dl className="profile-details">
          <dt>Estado técnico</dt><dd><Status value={info.status} /></dd><dt>Collector</dt><dd>{info.collector_name || "Sin asignar"}</dd>
          <dt>IP efectiva</dt><dd>{info.effective_ip || "Sin configurar"}</dd><dt>Latencia</dt><dd>{measure(info.last_latency_ms, "ms")}</dd>
          <dt>Pérdida</dt><dd>{measure(info.last_packet_loss_pct, "%")}</dd><dt>Última respuesta</dt><dd>{dateText(info.last_success_at)}</dd>
          <dt>Última comprobación</dt><dd>{dateText(info.last_check_at)}</dd>
        </dl>
        <div className="monitor-period"><Select label="Período" value={period} onChange={(event) => setPeriod(event.target.value)}>
          <option value="30m">Últimos 30 minutos</option><option value="1h">Última hora</option>
          <option value="24h">Últimas 24 horas</option><option value="7d">Últimos 7 días</option>
        </Select></div>
      </div>
      {info.eligibility_reason && <p className="description">{eligibility[info.eligibility_reason]}</p>}
      <p className="description">{info.series.filter((point) => point.valid_samples === 0).length} períodos sin datos suficientes.
        La disponibilidad se calcula sobre las comprobaciones válidas del período.</p>
      {info.series.some((point) => point.valid_samples > 0) && <div className="platform-columns">{charts.map(([key, title]) =>
        <section key={key} aria-label={title}><h3>{title}</h3><ResponsiveContainer width="100%" height={135}>
          <LineChart data={info.series}>
            <XAxis dataKey="bucket" minTickGap={16} tick={{ fontSize: 10 }} interval="preserveStartEnd"
              tickFormatter={(value: string) => ticks.format(new Date(value))} />
            <YAxis width={36} tick={{ fontSize: 10 }} domain={key === "latency" ? [0,"auto"] : [0,100]} />
            <Tooltip labelFormatter={(value) => dateText(String(value))} />
            <Line stroke="#6d28d9" name={title} dataKey={key} connectNulls={false}
              dot={info.series.filter((point) => point[key] !== null).length === 1 ? { r: 3 } : false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer></section>)}</div>}
    </div>
    <DataTable headers={["Fecha", "Destino", "Resultado", "Paquetes", "RTT medio", "Pérdida", "Transporte"]}
      empty={!info.samples.length ? "No hay mediciones para este período." : undefined}>
      {info.samples.map((sample, index) => <tr key={sample.checked_at + index}>
        <td>{dateText(sample.checked_at)}</td><td>{sample.ip || "—"}</td><td>{results[sample.result] ?? sample.result}</td>
        <td>{sample.packets_sent ? `${sample.packets_received}/${sample.packets_sent}` : "—"}</td>
        <td>{measure(sample.latency_ms, "ms")}</td><td>{measure(sample.packet_loss_pct, "%")}</td>
        <td>{sample.transport_healthy ? "Verificado" : "Sin validar"}</td>
      </tr>)}
    </DataTable></Panel>
    <Panel title="Incidentes"><IncidentTable items={info.incidents} links={false} /></Panel>
  </>}</DataView>
}
