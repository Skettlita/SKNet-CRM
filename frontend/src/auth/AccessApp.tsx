import { lazy, Suspense, useEffect, useState } from "react"
import { AdminConnectivity, IspConnectivity } from "../connectivity/Connectivity"

import { CrmCatalog } from "../enterprise/Catalog"
import { CrmDetail } from "../enterprise/Detail"
import { Installations } from "../enterprise/Installations"
import { catalogs } from "../enterprise/model"
import type { Kind } from "../enterprise/model"
import { FoundationDashboard } from "../FoundationDashboard"
import { CompanyDetail, CompanyList } from "../platform/Companies"
import { NewPlan, PlanDetail, PlanList } from "../platform/Plans"
import { SubscriptionDetail, SubscriptionList } from "../platform/Subscriptions"
import { CreateTicket, TicketDetail, TicketList } from "../platform/Support"
import { AppShell } from "../shared/AppShell"
import { Button } from "../shared/Button"
import { api, ApiError, homePath, loginPath, message } from "./api"
import type { Account, Scope } from "./api"
import { PageHeading, RoleManagement, UserManagement } from "./AccessManagement"
import { ManualRegistration, ProfilePage, SettingsPage, SupportResetPage } from "./PanelSettings"
import { ChangePasswordPage, LoginPage, RecoverPage, SignupPage } from "./PublicPages"

const IspDashboard = lazy(() => import("../enterprise/Reporting").then((module) => ({ default: module.IspDashboard })))
const InfrastructurePage = lazy(() => import("../enterprise/Reporting").then((module) => ({ default: module.InfrastructurePage })))
const MonitoringList = lazy(() => import("../enterprise/Monitoring").then((module) => ({ default: module.MonitoringList })))
const IncidentsPage = lazy(() => import("../enterprise/Monitoring").then((module) => ({ default: module.IncidentsPage })))
const AdminDashboard = lazy(() => import("../platform/Reporting").then((module) => ({ default: module.AdminDashboard })))
const AuditPage = lazy(() => import("../platform/Reporting").then((module) => ({ default: module.AuditPage })))

const pageConfig: Record<string, { title: string; permission?: string; scope?: Scope }> = {
  "": { title: "Dashboard", permission: "dashboard.read" },
  "/users": { title: "Usuarios", permission: "users.read" },
  "/roles": { title: "Roles y permisos", permission: "roles.read" },
  "/settings": { title: "Configuración", permission: "settings.read", scope: "admin" },
  "/system": { title: "Estado del sistema", permission: "system.read", scope: "admin" },
  "/companies": { title: "Empresas", permission: "companies.read", scope: "admin" },
  "/companies/:id": { title: "Empresa", permission: "companies.read", scope: "admin" },
  "/plans": { title: "Planes SaaS", permission: "plans.read", scope: "admin" },
  "/plans/new": { title: "Nuevo plan SaaS", permission: "plans.write", scope: "admin" },
  "/plans/:id": { title: "Plan SaaS", permission: "plans.read", scope: "admin" },
  "/subscriptions": { title: "Suscripciones", permission: "subscriptions.read", scope: "admin" },
  "/subscriptions/:id": { title: "Suscripción", permission: "subscriptions.read", scope: "admin" },
  "/support": { title: "Soporte", permission: "support.read" },
  "/support/new": { title: "Nueva solicitud", permission: "support.create", scope: "isp" },
  "/support/:id": { title: "Solicitud de soporte", permission: "support.read" },
  "/automatic-tickets": { title: "Tickets automáticos", permission: "support.read", scope: "admin" },
  "/audit": { title: "Auditoría", permission: "audit.read", scope: "admin" },
  "/companies/new": { title: "Nueva empresa", permission: "companies.create", scope: "admin" },
  "/support/reset": { title: "Recuperar acceso ISP", permission: "support.reset", scope: "admin" },
  "/infrastructure": { title: "Infraestructura", permission: "infrastructure.read", scope: "isp" },
  "/installations": { title: "Instalaciones", permission: "installations.read", scope: "isp" },
  "/installations/:id": { title: "Instalación", permission: "installations.read", scope: "isp" },
  "/connectivity": { title: "Conectividad", permission: "connectivity.read", scope: "isp" },
  "/monitoring": { title: "Monitoreo ICMP", permission: "monitoring.read", scope: "isp" },
  "/incidents": { title: "Incidentes", permission: "monitoring.read", scope: "isp" },
  "/collectors": { title: "Collectors", permission: "connectivity.read", scope: "admin" },
  "/vpn": { title: "Conectividad VPN", permission: "connectivity.read", scope: "admin" },
  "/network-pools": { title: "Recursos de red", permission: "connectivity.read", scope: "admin" },
  "/provisioning-jobs": { title: "Trabajos de aprovisionamiento", permission: "connectivity.read", scope: "admin" },
  "/profile": { title: "Perfil" },
  "/preferences": { title: "Preferencias" },
  "/password": { title: "Cambiar contraseña" },
}

function ProtectedPanel({ scope, route }: { scope: Scope; route: string }) {
  const [account, setAccount] = useState<Account | null>(null)
  const [error, setError] = useState("")
  const [check, setCheck] = useState(0)
  const refresh = () => setCheck((value) => value + 1)

  useEffect(() => {
    let alive = true
    api<Account>(scope, "/me").then((account) => {
      if (alive) { setAccount(account); setError("") }
    }).catch((error) => {
      if (!alive) return
      if (error instanceof ApiError && error.status === 401) window.location.replace(loginPath(scope))
      else { setAccount(null); setError(message(error)) }
    })
    return () => { alive = false }
  }, [scope, check])

  if (!account) return <main className="access-page"><div className="access-card">
    {error ? <><p className="form-error" role="alert">{error}</p><Button onClick={refresh}>Reintentar</Button></>
      : <p role="status">Verificando sesión…</p>}
  </div></main>

  if (account.must_change_password) {
    return <ChangePasswordPage scope={scope} required complete={() => window.location.replace(homePath(scope))} />
  }
  const match = /^\/(companies|plans|subscriptions|support|installations)\/([0-9a-f-]{36})$/i.exec(route)
  const key = match ? "/" + match[1] + "/:id" : route
  const id = match?.[2] ?? ""
  const crmMatch = /^\/(clients|internet-plans|services|sites|devices)(?:\/([0-9a-f-]{36}))?$/i.exec(route)
  const crmKind = crmMatch?.[1].toLowerCase() as Kind | undefined
  const crmId = crmMatch?.[2]
  const spec = crmKind ? catalogs[crmKind] : undefined
  const page = spec ? { title: spec.title, scope: "isp", permission: spec.permission + ".read" } : pageConfig[key]
  const allowed = page && (!page.scope || scope === page.scope) &&
    (!page.permission || account.permissions.includes(page.permission))

  let content
  if (!allowed) {
    const planInactive = account.plan && (!account.plan.current || !account.plan.access_enabled)
    content = <><PageHeading title={page ? "Acceso restringido" : "Página no encontrada"} />
      <p className="panel-message">{planInactive ? "Tu suscripción no habilita el acceso a este módulo."
        : page ? "Tu cuenta no tiene acceso a esta pantalla." : "Revisa la dirección o usa el menú lateral."}</p></>
  } else if (crmKind) {
    content = crmId ? <CrmDetail kind={crmKind} id={crmId} account={account} /> : <CrmCatalog kind={crmKind} account={account} />
  } else {
    switch (key) {
      case "/connectivity": content = <IspConnectivity account={account} />; break
      case "/monitoring": content = <MonitoringList account={account} />; break
      case "/incidents": content = <IncidentsPage account={account} />; break
      case "/installations": case "/installations/:id": content = <Installations account={account} id={id || undefined} />; break
      case "/collectors": content = <AdminConnectivity account={account} view="collectors" />; break
      case "/vpn": content = <AdminConnectivity account={account} view="vpn" />; break
      case "/network-pools": content = <AdminConnectivity account={account} view="pools" />; break
      case "/provisioning-jobs": content = <AdminConnectivity account={account} view="jobs" />; break
      case "/infrastructure": content = <InfrastructurePage account={account} />; break
      case "/companies": content = <CompanyList account={account} />; break
      case "/companies/:id": content = <CompanyDetail id={id} account={account} />; break
      case "/plans": content = <PlanList account={account} />; break
      case "/plans/new": content = <NewPlan />; break
      case "/plans/:id": content = <PlanDetail id={id} account={account} />; break
      case "/subscriptions": content = <SubscriptionList account={account} />; break
      case "/subscriptions/:id": content = <SubscriptionDetail id={id} account={account} />; break
      case "/support": content = <TicketList scope={scope} account={account} />; break
      case "/automatic-tickets": content = <TicketList scope="admin" account={account} automatic />; break
      case "/support/new": content = <CreateTicket account={account} />; break
      case "/support/:id": content = <TicketDetail id={id} scope={scope} account={account} />; break
      case "/audit": content = <AuditPage />; break
      case "/users": content = <UserManagement scope={scope} account={account} changed={refresh} />; break
      case "/roles": content = <RoleManagement scope={scope} account={account} changed={refresh} />; break
      case "/settings": content = <SettingsPage account={account} />; break
      case "/system": content = <FoundationDashboard />; break
      case "/companies/new": content = <ManualRegistration account={account} />; break
      case "/support/reset": content = <SupportResetPage />; break
      case "/profile": case "/preferences": case "/password":
        content = <ProfilePage scope={scope} account={account} changed={refresh}
          view={route.slice(1) as "profile" | "preferences" | "password"} />
        break
      default: content = scope === "admin" ? <AdminDashboard /> : <IspDashboard account={account} />
    }
  }
  return <AppShell account={account} scope={scope} title={allowed ? page.title : "SKNet"}><Suspense fallback={<p role="status">Cargando…</p>}>{content}</Suspense></AppShell>
}

export function AccessApp() {
  const path = window.location.pathname.replace(/\/$/, "") || "/"
  if (path === "/" || path === "/login") return <LoginPage scope="isp" />
  if (path === "/signup") return <SignupPage />
  if (path === "/recover") return <RecoverPage scope="isp" />
  if (path === "/admin/login") return <LoginPage scope="admin" />
  if (path === "/admin/recover") return <RecoverPage scope="admin" />
  if (path === "/app" || path.startsWith("/app/")) return <ProtectedPanel scope="isp" route={path.slice(4)} />
  if (path === "/admin" || path.startsWith("/admin/")) return <ProtectedPanel scope="admin" route={path.slice(6)} />
  return <main className="access-page"><section className="access-card">
    <h1>Página no encontrada</h1><a href="/login">Ir al inicio de sesión</a>
  </section></main>
}
