import { useEffect, useState } from "react"
import { Activity, Database, RefreshCw } from "lucide-react"

import { AppShell } from "./shared/AppShell"
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
    <AppShell>
      <section className="page-content">
        <div className="page-heading">
          <div>
            <h1>Dashboard</h1>
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
            <h2 id="system-title">Estado del sistema</h2>
          </div>
          <table className="device-table health-table">
            <thead><tr><th scope="col">Servicio</th><th scope="col">Estado</th></tr></thead>
            <tbody aria-live="polite">
              <tr><th scope="row"><Activity size={15} aria-hidden="true" /> API de SKNet</th><td><Status value={health.api} /></td></tr>
              <tr><th scope="row"><Database size={15} aria-hidden="true" /> PostgreSQL</th><td><Status value={health.database} /></td></tr>
            </tbody>
          </table>
        </section>
      </section>
    </AppShell>
  )
}
