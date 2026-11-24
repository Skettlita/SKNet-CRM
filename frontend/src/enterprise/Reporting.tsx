import { useState } from "react"
import { Activity, Building2, Cable, Cpu, MapPin, Users } from "lucide-react"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { PageHeading } from "../auth/AccessManagement"
import type { Account } from "../auth/api"
import { DataTable, DataView, Pagination, Panel, Search, Select, Status, dateText, searchPath, useData, usePager } from "../platform/shared"
import type { Page } from "../platform/shared"
import { allowed, appPath, crm, optionsLabel, roles, siteTypes } from "./model"

type Report = {
  clients?: { total: number; active: number }
  services?: { total: number; active: number; pending: number; suspended: number }
  sites?: number; devices?: number; monitoring?: { available: boolean }
  distribution?: { id: string; name: string; total: number }[]
  activity?: { id: string; actor: string | null; occurred_at: string; action: string; entity_type: string }[]
}

export function IspDashboard({ account }: { account: Account }) {
  const report = useData<Report>("isp", crm + "/dashboard")
  return <>
    <PageHeading title="Dashboard" description={account.company_name ?? "Resumen operativo del ISP."} />
    <DataView state={report}>{(data) => {
      const metrics = [
        { label: "Clientes registrados", value: data.clients?.total, icon: Users },
        { label: "Clientes activos", value: data.clients?.active, icon: Users },
        { label: "Servicios registrados", value: data.services?.total, icon: Cable },
        { label: "Servicios activos", value: data.services?.active, icon: Activity },
        { label: "Pendientes de instalación", value: data.services?.pending, icon: Cable },
        { label: "Servicios suspendidos", value: data.services?.suspended, icon: Cable },
        { label: "Sitios registrados", value: data.sites, icon: MapPin },
        { label: "Dispositivos registrados", value: data.devices, icon: Cpu },
      ].filter((item) => item.value !== undefined)
      return <>
        {metrics.length > 0 ? <div className="platform-metrics crm-metrics">
          {metrics.map(({ label, value, icon: Icon }) => <div className="metric-card" key={label}>
            <div><span>{label}</span><Icon size={16} aria-hidden="true" /></div>
            <strong>{value?.toLocaleString("es-BO")}</strong>
          </div>)}
        </div> : <Panel title="Primeros pasos"><div className="panel-body dashboard-start">
          {allowed(account, "users.read") && <a href="/app/users">Consultar usuarios</a>}
          {allowed(account, "roles.read") && <a href="/app/roles">Consultar roles y permisos</a>}
          <a href="/app/profile">Revisar mi perfil</a>
        </div></Panel>}
        <div className="platform-columns">
          {data.distribution && <Panel title="Distribución de servicios por plan">
            {data.distribution.length ? <>
              <div className="plan-chart" aria-hidden="true"><ResponsiveContainer width="100%" height={Math.min(230, 100 + 24 * data.distribution.length)}>
                <BarChart data={data.distribution.slice(0, 8)} layout="vertical" margin={{ right: 16 }}>
                  <CartesianGrid horizontal={false} stroke="#e5e7eb" />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                  <YAxis dataKey="name" type="category" width={95} tick={{ fontSize: 11 }} />
                  <Tooltip cursor={{ fill: "#ede9fe" }} />
                  <Bar dataKey="total" name="Servicios" fill="#6d28d9" radius={[0, 4, 4, 0]} maxBarSize={20} />
                </BarChart>
              </ResponsiveContainer></div>
              <DataTable headers={["Plan", "Servicios"]}>{data.distribution.map((item) =>
                <tr key={item.id}><td>{item.name}</td><td>{item.total}</td></tr>)}</DataTable>
            </> : <p className="panel-message">Todavía no hay servicios contratados para distribuir.</p>}
          </Panel>}
          {data.activity && <Panel title="Actividad reciente">
            <DataTable headers={["Fecha", "Usuario", "Acción"]} empty={!data.activity.length ? "Todavía no hay actividad registrada." : undefined}>
              {data.activity.map((item) => <tr key={item.id}><td>{dateText(item.occurred_at)}</td>
                <td>{item.actor || "Sistema"}</td><td>{item.action}</td></tr>)}
            </DataTable>
          </Panel>}
        </div>
        {data.monitoring && <Panel title="Disponibilidad y monitoreo">
          <p className="panel-message">Sin mediciones. La comprobación de dispositivos se habilitará junto con el collector.</p>
        </Panel>}
      </>
    }}</DataView>
  </>
}

type InfrastructureRow = {
  site_id: string; site_name: string; site_type: string; site_active: boolean
  device_id: string | null; device_name: string | null; device_role: string | null; device_active: boolean | null
}

export function InfrastructurePage({ account }: { account: Account }) {
  const [q, setQuery] = useState("")
  const [role, setRole] = useState("")
  const pager = usePager()
  const data = useData<Page<InfrastructureRow>>("isp", searchPath(crm + "/infrastructure", pager.offset, { q, role }))
  return <>
    <PageHeading title="Infraestructura de red" description="Ubicaciones propias y los dispositivos registrados en cada una." />
    <Panel>
      <div className="table-controls platform-filters">
        <Search label="Buscar sitio o dispositivo" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} />
        <Select label="Rol de dispositivo" value={role} onChange={(event) => { setRole(event.target.value); pager.setOffset(0) }}>
          <option value="">Todos</option>{roles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
      </div>
      <DataView state={data}>{({ items, has_more }) => <>
        <DataTable headers={["Sitio propio", "Tipo de sitio", "Estado del sitio", "Dispositivo", "Rol", "Estado del dispositivo"]}
          empty={!items.length ? "No hay sitios de infraestructura que coincidan." : undefined}>
          {items.map((item) => <tr key={item.site_id + (item.device_id || "")}>
            <td>{allowed(account, "sites.read") ? <a className="platform-link" href={appPath("sites", item.site_id)}>
              <Building2 size={14} className="crm-table-icon" />{item.site_name}</a> : item.site_name}</td>
            <td>{optionsLabel(siteTypes, item.site_type)}</td><td><Status value={item.site_active ? "ACTIVE" : "INACTIVE"} /></td>
            <td>{item.device_id && allowed(account, "devices.read") ? <a className="platform-link" href={appPath("devices", item.device_id)}>
              {item.device_name}</a> : item.device_name || "Sin dispositivos"}</td>
            <td>{optionsLabel(roles, item.device_role)}</td><td>{item.device_id ? <Status value={item.device_active ? "ACTIVE" : "INACTIVE"} /> : "—"}</td>
          </tr>)}
        </DataTable>
        <Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}
