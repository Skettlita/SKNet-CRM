import { useEffect, useState } from "react"

import { FoundationDashboard } from "../FoundationDashboard"
import { AppShell } from "../shared/AppShell"
import { Button } from "../shared/Button"
import { api, ApiError, homePath, loginPath, message } from "./api"
import type { Account, Scope } from "./api"
import { PageHeading, RoleManagement, UserManagement } from "./AccessManagement"
import { ManualRegistration, ProfilePage, SettingsPage, SupportResetPage } from "./PanelSettings"
import { ChangePasswordPage, LoginPage, RecoverPage, SignupPage } from "./PublicPages"

const pageConfig: Record<string, { title: string; permission?: string; admin?: boolean }> = {
  "": { title: "Dashboard", permission: "dashboard.read" },
  "/users": { title: "Usuarios", permission: "users.read" },
  "/roles": { title: "Roles y permisos", permission: "roles.read" },
  "/settings": { title: "Configuración", permission: "settings.read", admin: true },
  "/system": { title: "Estado del sistema", permission: "system.read", admin: true },
  "/companies/new": { title: "Nueva empresa", permission: "companies.create", admin: true },
  "/support/reset": { title: "Recuperar acceso ISP", permission: "support.reset", admin: true },
  "/profile": { title: "Perfil" },
  "/preferences": { title: "Preferencias" },
  "/password": { title: "Cambiar contraseña" },
}

function Home({ account, scope }: { account: Account; scope: Scope }) {
  return <>
    <PageHeading title="Dashboard" description={account.company_name ?? "Administración de la plataforma SKNet."} />
    <div className="table-panel"><div className="panel-header"><h2>Primeros pasos</h2></div>
      <div className="panel-body dashboard-start">
        {account.permissions.includes("users.read") && <a href={homePath(scope) + "/users"}>Consultar usuarios</a>}
        {account.permissions.includes("roles.read") && <a href={homePath(scope) + "/roles"}>Consultar roles y permisos</a>}
        {account.permissions.includes("settings.read") && <a href="/admin/settings">Consultar configuración del registro</a>}
        <a href={homePath(scope) + "/profile"}>Revisar mi perfil</a>
      </div>
    </div>
  </>
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
  const page = pageConfig[route]
  const allowed = page && (!page.admin || scope === "admin") &&
    (!page.permission || account.permissions.includes(page.permission))

  let content
  if (!allowed) {
    const planInactive = account.plan && (!account.plan.current || !account.plan.access_enabled)
    content = <><PageHeading title={page ? "Acceso restringido" : "Página no encontrada"} />
      <p className="panel-message">{planInactive ? "Tu suscripción no habilita el acceso a este módulo."
        : page ? "Tu cuenta no tiene acceso a esta pantalla." : "Revisa la dirección o usa el menú lateral."}</p></>
  } else {
    switch (route) {
      case "/users": content = <UserManagement scope={scope} account={account} changed={refresh} />; break
      case "/roles": content = <RoleManagement scope={scope} account={account} changed={refresh} />; break
      case "/settings": content = <SettingsPage account={account} />; break
      case "/system": content = <FoundationDashboard />; break
      case "/companies/new": content = <ManualRegistration />; break
      case "/support/reset": content = <SupportResetPage />; break
      case "/profile": case "/preferences": case "/password":
        content = <ProfilePage scope={scope} account={account} changed={refresh}
          view={route.slice(1) as "profile" | "preferences" | "password"} />
        break
      default: content = <Home account={account} scope={scope} />
    }
  }
  return <AppShell account={account} scope={scope} title={allowed ? page.title : "SKNet"}>{content}</AppShell>
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
