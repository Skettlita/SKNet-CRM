import { useEffect, useState } from "react"
import { Activity, Database, RefreshCw } from "lucide-react"

import { DataTable, DataView, dateText, Panel, useData } from "./platform/shared"
import { Button } from "./shared/Button"

type Availability = "checking" | "ok" | "unavailable" | "unknown"
type Health = { api: Availability; database: Availability }

const labels: Record<Availability, string> = {
  checking: "Comprobando",
  ok: "Disponible",
  unavailable: "No disponible",
  unknown: "Sin información",
}

async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch("/api/v1/health", { signal, cache: "no-store" })
  const result: unknown = await response.json()

  if (typeof result === "object" && result !== null && "status" in result && "database" in result) {
    if (response.ok && result.status === "ok" && result.database === "ok") {
      return { api: "ok", database: "ok" }
    }
    if (response.status === 503 && result.status === "unavailable" && result.database === "unavailable") {
      return { api: "ok", database: "unavailable" }
    }
  }

  return { api: "unavailable", database: "unknown" }
}

function Status({ value }: { value: Availability }) {
  const tone = value === "ok" ? "up" : value === "unavailable" ? "down" : "muted"
  return <span className={`status status-${tone}`}><i aria-hidden="true" />{labels[value]}</span>
}

export function FoundationDashboard() {
  const [health, setHealth] = useState<Health>({ api: "checking", database: "checking" })
  const [request, setRequest] = useState(0)
  const infrastructure = useData<{ mode: string; observed_at: string | null; failures: number; jobs: number; tickets: number }>(
    "admin", "/connectivity/system", request,
  )

  useEffect(() => {
    const controller = new AbortController()
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(6000)])

    fetchHealth(signal)
      .then((result) => { if (!controller.signal.aborted) setHealth(result) })
      .catch(() => {
        if (!controller.signal.aborted) setHealth({ api: "unavailable", database: "unknown" })
      })

    return () => controller.abort()
  }, [request])

  return (
    <>
        <div className="page-heading">
          <div>
            <h1>Estado del sistema</h1>
            <p>Estado de la instalación de SKNet.</p>
          </div>
          <Button
            disabled={health.api === "checking"}
            onClick={() => {
              setHealth({ api: "checking", database: "checking" })
              setRequest(request + 1)
            }}
          >
            <RefreshCw size={14} aria-hidden="true" /> Actualizar
          </Button>
        </div>

        <section className="table-panel" aria-labelledby="system-title">
          <div className="panel-header">
            <h2 id="system-title">Servicios base</h2>
          </div>
          <table className="device-table health-table">
            <thead><tr><th scope="col">Servicio</th><th scope="col">Estado</th></tr></thead>
            <tbody aria-live="polite">
              <tr><th scope="row"><Activity size={15} aria-hidden="true" /> API de SKNet</th><td><Status value={health.api} /></td></tr>
              <tr><th scope="row"><Database size={15} aria-hidden="true" /> PostgreSQL</th><td><Status value={health.database} /></td></tr>
            </tbody>
          </table>
        </section>
        <Panel title="Aprovisionamiento de red"><DataView state={infrastructure}>{(data) => {
          const recent = data.observed_at && Date.now() - new Date(data.observed_at).getTime() < 60000
          const worker = data.mode === "disabled" ? "Deshabilitado" : recent ? "Disponible" : "Sin datos recientes"
          return <DataTable headers={["Componente", "Estado"]}>
            <tr><th scope="row">Provisioner</th><td>{worker} · {dateText(data.observed_at)}</td></tr>
            <tr><th scope="row">Adaptador NAT</th><td>{data.mode === "simulation" ? "Simulación DEV" : data.mode === "routeros" ? "RouterOS" : "Deshabilitado"}</td></tr>
            <tr><th scope="row">Trabajos en curso</th><td>{data.jobs}</td></tr>
            <tr><th scope="row">Collectors con error</th><td>{data.failures}</td></tr>
            <tr><th scope="row">Tickets automáticos abiertos</th><td>{data.tickets}</td></tr>
          </DataTable>
        }}</DataView></Panel>
    </>
  )
}
