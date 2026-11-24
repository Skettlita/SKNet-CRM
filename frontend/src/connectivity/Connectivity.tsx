import { useEffect, useState } from "react"

import { PageHeading } from "../auth/AccessManagement"
import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { ActionForm, Field } from "../auth/forms"
import { DataTable, DataView, dateText, Pagination, Panel, Status, TextArea, textValue, useData, usePager } from "../platform/shared"
import type { Page } from "../platform/shared"
import { Button } from "../shared/Button"

type Collector = {
  id: string; company_id: string; company_name: string; networks: string[]; enabled: boolean
  provisioning_status: string; provisioning_step: string; container_state: string; connection_status: string | null
  last_heartbeat_at: string | null; heartbeat_fresh: boolean; last_handshake_at: string | null; last_probe_at: string | null
  diagnostic: string | null; simulated: boolean; job_status: string | null; ticket_id: string | null
  script_available: boolean; simulation_preview: boolean; peer_configured: boolean
  docker_subnet: string | null; docker_ip: string | null; wireguard_subnet: string | null; external_udp_port: number | null
}
type Job = { id: string; company_name: string; operation: string; status: string; attempts: number
  created_at: string; finished_at: string | null; error_code: string | null }
type Pools = { mode: string; reserved: number; items: { name: string; pool: string; total: number; available: number }[] }

const labels: Record<string, string> = {
  QUEUED: "En cola", RESERVING: "Reservando redes y puerto", KEYS: "Preparando claves",
  NETWORK: "Creando red Docker", CONTAINER: "Arrancando el collector", NAT: "Configurando NAT",
  VERIFYING: "Verificando WireGuard y heartbeat", RETIRING: "Retirando recursos",
  COMPLETE: "Verificado", FAILED: "Fallido", CREATE: "Creación", CONFIGURE: "Configuración del router",
  RECONCILE: "Reconciliación", ROTATE_KEY: "Rotación del token", DISABLE: "Deshabilitación", REMOVE: "Retiro",
  NO_PEER: "Esperando la clave pública del router", WG_ERROR: "WireGuard no pudo aplicar la configuración",
  NO_HANDSHAKE: "Sin handshake reciente", NO_REPLY: "El router no respondió al ping del túnel", OK: "Diagnóstico correcto",
  DOCKER_POOL: "Sin subredes Docker disponibles", WG_POOL: "Sin subredes WireGuard disponibles", UDP_POOL: "Sin puertos UDP disponibles",
  PORT_CONFLICT: "El puerto UDP está ocupado", ROUTEROS_FAILED: "No se pudo verificar NAT o firewall",
  COLLECTOR_STALE: "Señal de vida vencida", ROUTE_CONFLICT: "Una red remota coincide con una red protegida",
  DOCKER_FAILED: "No se pudo verificar el collector", KEY_FAILED: "No se pudieron preparar claves",
  LEASE_EXPIRED: "Venció el tiempo de aprovisionamiento", CONFIGURATION: "Configuración de instalación incompatible",
  RETIRE_FAILED: "El retiro falló y los recursos siguen reservados",
}
const label = (value: string | null) => value ? labels[value] ?? value : "—"
const networks = (fields: FormData) => textValue(fields, "networks").split(/[\s,]+/).filter(Boolean)
const vpn = (item: Collector) => item.simulated ? "SIMULATED" : item.heartbeat_fresh ? item.connection_status ?? "UNKNOWN" : "STALE"
const ticket = (id: string, base: string, canRead: boolean) => canRead ? <a href={base + "/support/" + id}>{id}</a> : id

export function IspConnectivity({ account }: { account: Account }) {
  const { version, reload } = usePager()
  const state = useData<Collector | null>("isp", "/connectivity", version)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(false)
  const [script, setScript] = useState("")
  const [copyState, setCopyState] = useState("")
  const canWrite = account.permissions.includes("connectivity.write")

  useEffect(() => {
    const timer = window.setInterval(reload, 5000)
    return () => window.clearInterval(timer)
  }, [])

  function download() {
    const url = URL.createObjectURL(new Blob([script], { type: "text/plain" }))
    const link = document.createElement("a")
    link.href = url
    link.download = "sknet-routeros.rsc"
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <><PageHeading title="Conectividad" /><DataView state={state}>{(item) => {
    if (!item) return <Panel title="Conecta tu red"><div className="panel-body">
      <p>SKNet preparará un collector y un túnel privado WireGuard para las redes de tu empresa.</p>
      {canWrite && (creating ? <ActionForm label="Generar script" cancel={() => setCreating(false)} submit={async (fields) => {
        await api("isp", "/connectivity", "POST", { networks: networks(fields) })
        setCreating(false)
        reload()
      }}><TextArea name="networks" label="Subredes IPv4 privadas en formato CIDR. Ej. 192.168.40.0/24" maxLength={1024} required />
        <p>La clave pública del MikroTik con RouterOS 7 se registra después de preparar el túnel.</p>
      </ActionForm> : <Button variant="primary" onClick={() => setCreating(true)}>Conectar mi red</Button>)}
    </div></Panel>

    const ready = item.script_available || item.simulation_preview
    return <>
      <Panel title="Estado de la conexión"><div className="panel-body" aria-live="polite">
        {item.simulated && <p><Status value="SIMULATED" /> NAT de prueba en DEV</p>}
        <dl className="detail-grid">
          <dt>Aprovisionamiento</dt><dd><Status value={item.provisioning_status} /> · {label(item.provisioning_step)}</dd>
          <dt>Trabajo</dt><dd><Status value={item.job_status ?? "UNKNOWN"} /></dd>
          <dt>Contenedor</dt><dd><Status value={item.container_state} /></dd>
          <dt>VPN</dt><dd><Status value={vpn(item)} /></dd>
          <dt>Redes autorizadas</dt><dd>{item.networks.join(", ")}</dd>
          <dt>Última comunicación</dt><dd>{dateText(item.last_heartbeat_at)}</dd>
          <dt>Último handshake</dt><dd>{dateText(item.last_handshake_at)}</dd>
          <dt>Último diagnóstico</dt><dd>{label(item.diagnostic)} · {dateText(item.last_probe_at)}</dd>
          {item.ticket_id && <><dt>Referencia de soporte</dt><dd>{ticket(item.ticket_id, "/app", account.permissions.includes("support.read"))}</dd></>}
        </dl>
        {item.job_status === "FAILED" && <p className="form-error" role="alert">Servicio temporalmente en mantenimiento. El equipo técnico de SKNet ha sido notificado.</p>}
        {canWrite && item.enabled && item.job_status === "FAILED" && <ActionForm label="Reintentar" submit={async () => {
          await api("isp", "/connectivity/retry", "POST")
          reload()
        }} />}
      </div></Panel>
      {ready && <Panel title="Script para MikroTik RouterOS 7"><div className="panel-body">
        <ActionForm label={item.simulation_preview ? "Consultar vista previa" : "Consultar script"} submit={async () => {
          const result = await api<{ script: string }>("isp", "/connectivity/script" + (item.simulation_preview ? "?preview=true" : ""))
          setScript(result.script)
          setCopyState("")
        }} />
        {script && <><pre className="connectivity-script">{script}</pre>
          {item.script_available && <div className="form-actions">
            <Button onClick={async () => {
              try { await navigator.clipboard.writeText(script); setCopyState("Script copiado.") }
              catch { setCopyState("No se pudo copiar. Puedes descargar el archivo.") }
            }}>Copiar</Button><Button onClick={download}>Descargar .rsc</Button>
            <span role="status">{copyState}</span>
          </div>}
        </>}
      </div></Panel>}
      {ready && canWrite && <Panel title={item.peer_configured ? "Configuración del router" : "Registrar clave pública"}>
        <div className="panel-body">{(!item.peer_configured || editing) ?
          <ActionForm label="Guardar configuración" cancel={item.peer_configured ? () => setEditing(false) : undefined} submit={async (fields) => {
            const key = textValue(fields, "public_key")
            if (key) await api("isp", "/connectivity/peer", "PUT", { networks: networks(fields), public_key: key })
            else await api("isp", "/connectivity/routes", "PUT", { networks: networks(fields) })
            setEditing(false)
            reload()
          }}>
            <Field name="public_key" label={item.peer_configured ? "Nueva clave pública (opcional)" : "Clave pública WireGuard del MikroTik"} minLength={44} maxLength={44} required={!item.peer_configured} />
            <TextArea name="networks" label="Redes remotas autorizadas (CIDR)" defaultValue={item.networks.join("\n")} maxLength={1024} required />
          </ActionForm> : <Button onClick={() => setEditing(true)}>Actualizar clave pública o redes</Button>}
        </div>
      </Panel>}
    </>
  }}</DataView></>
}

export function AdminConnectivity({ account, view }: { account: Account; view: "collectors" | "vpn" | "pools" | "jobs" }) {
  const { offset, setOffset, version, reload } = usePager()
  const collectors = useData<Page<Collector>>("admin", view === "collectors" || view === "vpn" ? "/connectivity/collectors?offset=" + offset : null, version)
  const jobs = useData<Page<Job>>("admin", view === "jobs" ? "/connectivity/jobs?offset=" + offset : null, version)
  const pools = useData<Pools>("admin", view === "pools" ? "/connectivity/pools" : null, version)
  const [action, setAction] = useState<{ id: string; command: string; title: string } | null>(null)
  const titles = { collectors: "Collectors", vpn: "Conectividad VPN", pools: "Recursos de red", jobs: "Trabajos de aprovisionamiento" }
  const canWrite = account.permissions.includes("connectivity.write")
  const isVpn = view === "vpn"

  return <><PageHeading title={titles[view]} action={<Button onClick={reload}>Actualizar</Button>} />
    {view === "pools" && <Panel><DataView state={pools}>{(data) => <>
      <p className="panel-message">Modo {data.mode === "simulation" ? "simulación DEV" : data.mode === "routeros" ? "RouterOS" : "deshabilitado"} · {data.reserved} reservas vigentes</p>
      <DataTable headers={["Recurso", "Pool", "Capacidad", "Ocupados o bloqueados", "Disponibles"]}>
        {data.items.map((item) => <tr key={item.name}><td>{item.name}</td><td>{item.pool}</td><td>{item.total}</td><td>{item.total - item.available}</td><td>{item.available}</td></tr>)}
      </DataTable>
    </>}</DataView></Panel>}
    {view === "jobs" && <Panel><DataView state={jobs}>{(data) => <>
      <DataTable headers={["Empresa", "Operación", "Estado", "Intentos", "Creado", "Finalizado", "Diagnóstico"]} empty={data.items.length ? undefined : "No hay trabajos."}>
        {data.items.map((item) => <tr key={item.id}><td>{item.company_name}</td><td>{label(item.operation)}</td>
          <td><Status value={item.status} /></td><td>{item.attempts}</td><td>{dateText(item.created_at)}</td>
          <td>{dateText(item.finished_at)}</td><td>{label(item.error_code)}</td></tr>)}
      </DataTable><Pagination offset={offset} more={data.has_more} onChange={setOffset} />
    </>}</DataView></Panel>}
    {(view === "collectors" || isVpn) && <Panel><DataView state={collectors}>{(data) => <>
      <DataTable headers={isVpn ? ["Empresa", "VPN", "WireGuard", "Redes autorizadas", "Handshake", "Diagnóstico"] :
        ["Empresa", "Aprovisionamiento", "Contenedor", "Red Docker", "IP", "UDP", "Heartbeat", "Diagnóstico", "Acciones"]}
        empty={data.items.length ? undefined : "No hay collectors."}>
        {data.items.map((item) => <tr key={item.id}><td>{item.company_name}{item.simulated && <div><Status value="SIMULATED" /></div>}</td>
          {isVpn ? <><td><Status value={vpn(item)} /></td><td>{item.wireguard_subnet ?? "—"}</td><td>{item.networks.join(", ")}</td>
            <td>{dateText(item.last_handshake_at)}</td><td>{label(item.diagnostic)}</td></> :
            <><td><Status value={item.provisioning_status} /></td><td><Status value={item.container_state} /></td>
              <td>{item.docker_subnet ?? "—"}</td><td>{item.docker_ip ?? "—"}</td><td>{item.external_udp_port ?? "—"}</td><td>{dateText(item.last_heartbeat_at)}</td>
              <td>{label(item.diagnostic)}{item.ticket_id && <div>{ticket(item.ticket_id, "/admin", account.permissions.includes("support.read"))}</div>}</td>
              <td>{canWrite && !["PENDING", "RUNNING"].includes(item.job_status ?? "") && <div className="form-actions">
                {(item.job_status === "FAILED" ? [["retry", "Reintentar"]] :
                  item.enabled ? [["rotate", "Rotar token"], ["disable", "Deshabilitar"]] : [["remove", "Retirar recursos"]])
                  .map(([command, title]) => <Button key={command} onClick={() => setAction({ id: item.id, command, title })}>{title}</Button>)}
              </div>}</td></>}
        </tr>)}
      </DataTable><Pagination offset={offset} more={data.has_more} onChange={setOffset} />
      {action && data.items.filter((item) => item.id === action.id).map((item) =>
        <div className="panel-body" key={item.id}><h3>{action.title} · {item.company_name}</h3>
          <ActionForm label="Confirmar" cancel={() => setAction(null)} submit={async () => {
            await api("admin", "/connectivity/collectors/" + item.company_id + "/" + item.id + "/" + action.command, "POST")
            setAction(null)
            reload()
          }} />
        </div>)}
    </>}</DataView></Panel>}
  </>
}
