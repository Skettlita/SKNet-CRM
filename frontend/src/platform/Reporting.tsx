import { useState } from "react"
import type { ReactNode } from "react"
import { Activity, Building2, ChartNoAxesCombined, CircleAlert, CreditCard, LifeBuoy, Network, Users } from "lucide-react"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { PageHeading } from "../auth/AccessManagement"
import {
  DataTable, DataView, Pagination, Panel, Search, Select, dateText, searchPath, useData, usePager,
} from "./shared"
import type { Choice, Page } from "./shared"

type ActivityEntry = {
  id: string; company_id: string | null; actor: string | null; scope: string; action: string
  entity_type: string; entity_id: string | null; occurred_at: string
}
type AuditEvent = ActivityEntry & { before_data: object | null; after_data: object | null; reason: string | null }
type Dashboard = {
  companies?: { registered: number; active: number; suspended: number }
  subscriptions?: { active: number; trial: number; revenue_available: boolean; distribution: { code: string; name: string; companies: number }[] }
  staff_users?: number; isp_users?: number; open_tickets?: number; activity?: ActivityEntry[]
  infrastructure?: { collectors: number; connected: number; last_measurement: string | null }
}

export function AdminDashboard() {
  const report = useData<Dashboard>("admin", "/dashboard")
  return <>
    <PageHeading title="Dashboard" description="Resumen operativo de la plataforma SKNet." />
    <DataView state={report}>{(data) => {
      const metrics: { label: string; value: number; icon: ReactNode }[] = []
      if (data.companies) metrics.push(
        { label: "Empresas registradas", value: data.companies.registered, icon: <Building2 size={17} /> },
        { label: "Empresas activas", value: data.companies.active, icon: <Activity size={17} /> },
        { label: "Empresas suspendidas", value: data.companies.suspended, icon: <CircleAlert size={17} /> },
      )
      if (data.subscriptions) metrics.push(
        { label: "Suscripciones vigentes", value: data.subscriptions.active, icon: <CreditCard size={17} /> },
        { label: "Empresas con plan de prueba", value: data.subscriptions.trial, icon: <ChartNoAxesCombined size={17} /> },
      )
      if (data.staff_users !== undefined) metrics.push({ label: "Usuarios SaaS", value: data.staff_users, icon: <Users size={17} /> })
      if (data.isp_users !== undefined) metrics.push({ label: "Usuarios ISP", value: data.isp_users, icon: <Users size={17} /> })
      if (data.open_tickets !== undefined) metrics.push({ label: "Tickets abiertos", value: data.open_tickets, icon: <LifeBuoy size={17} /> })
      return <>
        {metrics.length > 0 && <div className="platform-metrics">
          {metrics.map((metric) => <div className="metric-card" key={metric.label}>
            <div><span>{metric.label}</span>{metric.icon}</div><strong>{metric.value.toLocaleString("es-BO")}</strong>
          </div>)}
        </div>}
        <div className="platform-columns">
          {data.subscriptions && <Panel title="Distribución de empresas por plan">
            {data.subscriptions.distribution.length ? <>
              <div className="plan-chart" aria-hidden="true"><ResponsiveContainer width="100%" height={190}>
                <BarChart data={data.subscriptions.distribution.slice(0, 8)} layout="vertical" margin={{ left: 4, right: 16 }}>
                  <CartesianGrid stroke="#e5e7eb" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                  <YAxis dataKey="code" type="category" width={84} tick={{ fontSize: 11 }} />
                  <Tooltip cursor={{ fill: "#ede9fe" }} />
                  <Bar dataKey="companies" name="Empresas" fill="#6d28d9" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer></div>
              <DataTable headers={["Plan", "Empresas"]}>
                {data.subscriptions.distribution.map((item) => <tr key={item.code}><td>{item.name}</td><td>{item.companies}</td></tr>)}
              </DataTable>
            </> : <p className="panel-message">Todavía no hay suscripciones vigentes.</p>}
            {!data.subscriptions.revenue_available && <p className="panel-message description">Ingresos: no disponibles en esta fase.</p>}
          </Panel>}
          {data.activity && <Panel title="Actividad administrativa reciente">
            <DataTable headers={["Fecha", "Usuario", "Acción"]}
              empty={!data.activity.length ? "Todavía no hay actividad registrada." : undefined}>
              {data.activity.map((entry) => <tr key={entry.id}>
                <td>{dateText(entry.occurred_at)}</td><td>{entry.actor ?? "Sistema"}</td><td>{entry.action}</td>
              </tr>)}
            </DataTable>
          </Panel>}
        </div>
        {data.infrastructure && <Panel title="Infraestructura">
          <div className="panel-body">
            <dl className="profile-details"><dt><Network size={14} /> Collectors registrados</dt><dd>{data.infrastructure.collectors}</dd>
              <dt>Conexiones verificadas</dt><dd>{data.infrastructure.connected}</dd>
              <dt>Monitoreo</dt><dd>{data.infrastructure.last_measurement ? `Última medición: ${dateText(data.infrastructure.last_measurement)}` : "Sin mediciones"}</dd>
            </dl>
          </div>
        </Panel>}
        {!Object.keys(data).length && <p className="panel-message">Tu cuenta aún no tiene indicadores disponibles.</p>}
      </>
    }}</DataView>
  </>
}

export function AuditPage() {
  const [q, setQuery] = useState("")
  const [company, setCompany] = useState("")
  const [scope, setScope] = useState("")
  const [selected, setSelected] = useState<AuditEvent | null>(null)
  const pager = usePager()
  const choices = useData<Choice[]>("admin", "/companies/options")
  const state = useData<Page<AuditEvent>>("admin", searchPath("/audit", pager.offset, { q, company_id: company, scope }))
  return <>
    <PageHeading title="Auditoría" description="Consulta de operaciones registradas por SKNet." />
    {selected && <Panel title="Detalle de auditoría"><div className="panel-body">
      <dl className="profile-details">
        <dt>Fecha</dt><dd>{dateText(selected.occurred_at)}</dd><dt>Usuario</dt><dd>{selected.actor ?? "Sistema"}</dd>
        <dt>Ámbito</dt><dd>{selected.scope}</dd><dt>Acción</dt><dd>{selected.action}</dd>
        <dt>Entidad</dt><dd>{selected.entity_type} {selected.entity_id ?? ""}</dd>
        {selected.reason && <><dt>Motivo</dt><dd>{selected.reason}</dd></>}
      </dl>
      <div className="platform-columns audit-changes">
        <div><strong>Antes</strong><pre>{selected.before_data ? JSON.stringify(selected.before_data, null, 2) : "—"}</pre></div>
        <div><strong>Después</strong><pre>{selected.after_data ? JSON.stringify(selected.after_data, null, 2) : "—"}</pre></div>
      </div>
      <button type="button" className="button button-outline" onClick={() => setSelected(null)}>Cerrar detalle</button>
    </div></Panel>}
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar usuario, acción o entidad" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} />
        <Select label="Empresa" value={company} onChange={(event) => { setCompany(event.target.value); pager.setOffset(0) }}>
          <option value="">Todas</option>{choices.data?.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
        </Select>
        <Select label="Ámbito" value={scope} onChange={(event) => { setScope(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option><option value="SAAS">SaaS</option><option value="ISP">ISP</option><option value="SYSTEM">Sistema</option>
        </Select>
      </div>
      {choices.error && <p className="panel-message form-error" role="alert">{choices.error}</p>}
      <DataView state={state}>{({ items, has_more }) => <>
        <DataTable headers={["Fecha", "Usuario", "Ámbito", "Acción", "Entidad", "Detalle"]}
          empty={!items.length ? "No hay registros que coincidan." : undefined}>
          {items.map((item) => <tr key={item.id}>
            <td>{dateText(item.occurred_at)}</td><td>{item.actor ?? "Sistema"}</td><td>{item.scope}</td>
            <td>{item.action}</td><td>{item.entity_type}</td>
            <td><button type="button" className="button button-outline" onClick={() => setSelected(item)}>Consultar</button></td>
          </tr>)}
        </DataTable>
        <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}
