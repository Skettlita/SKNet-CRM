import { useState } from "react"
import type { ReactNode } from "react"
import {
  Activity, Building2, ChevronDown, ChevronLeft, ChevronRight, KeyRound, LayoutDashboard,
  LifeBuoy, LogOut, Menu, Network, Settings, ShieldCheck, SlidersHorizontal, User, Users, X,
} from "lucide-react"

import { api, homePath, loginPath, message } from "../auth/api"
import type { Account, Scope } from "../auth/api"

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <>
      <span className="brand-mark" aria-hidden="true"><Network size={19} strokeWidth={2.4} /></span>
      <span className={compact ? "sr-only" : "brand-copy"}>
        <b>SK<span>Net</span></b>
        <small>GESTIÓN DE RED</small>
      </span>
    </>
  )
}

const groups = [
  { label: "General", items: [{ title: "Dashboard", route: "", icon: LayoutDashboard, permission: "dashboard.read" }] },
  { label: "Plataforma", items: [{ title: "Nueva empresa", route: "/companies/new", icon: Building2, permission: "companies.create" }] },
  { label: "Infraestructura", items: [{ title: "Estado del sistema", route: "/system", icon: Activity, permission: "system.read" }] },
  { label: "Administración", items: [
    { title: "Usuarios", route: "/users", icon: Users, permission: "users.read" },
    { title: "Roles y permisos", route: "/roles", icon: ShieldCheck, permission: "roles.read" },
    { title: "Configuración", route: "/settings", icon: Settings, permission: "settings.read" },
    { title: "Recuperar acceso ISP", route: "/support/reset", icon: LifeBuoy, permission: "support.reset" },
  ] },
]

export function AppShell({ children, account, scope, title }: {
  children: ReactNode; account: Account; scope: Scope; title: string
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [closed, setClosed] = useState<string[]>([])
  const [mobileOpen, setMobileOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState("")
  const base = homePath(scope)

  async function logout() {
    setSigningOut(true)
    try {
      await api(scope, "/logout", "POST")
      window.location.replace(loginPath(scope))
    } catch (error) {
      setError(message(error))
      setSigningOut(false)
    }
  }

  return (
    <div className={`app-shell ${account.compact_view ? "compact-view" : ""}`}>
      <aside id="main-sidebar"
        className={`sidebar ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`}
        onKeyDown={(event) => { if (event.key === "Escape") setMobileOpen(false) }}>
        <div className="brand">
          <Brand compact={collapsed} />
          <button type="button" className="collapse-btn" onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Expandir menú" : "Contraer menú"} aria-expanded={!collapsed} aria-controls="main-navigation">
            <ChevronLeft size={15} className={collapsed ? "rotate" : ""} />
          </button>
          <button type="button" className="mobile-menu" onClick={() => setMobileOpen(false)} aria-label="Cerrar menú"><X size={18} /></button>
        </div>
        <nav id="main-navigation" className="side-nav" aria-label="Navegación principal">
          {groups.map(({ label, items }, index) => {
            const available = items.filter(({ permission }) => account.permissions.includes(permission))
            if (available.length === 0) return null
            const expanded = collapsed || !closed.includes(label)
            return <div className="nav-group" key={label}>
              {!collapsed && <button type="button" className="nav-heading group-toggle"
                aria-expanded={expanded} aria-controls={`nav-group-${index}`}
                onClick={() => setClosed(expanded ? [...closed, label] : closed.filter((group) => group !== label))}>
                {label}<ChevronDown size={13} className={expanded ? "" : "group-closed"} />
              </button>}
              <div id={`nav-group-${index}`} hidden={!expanded}>
                {available.map(({ title, icon: Icon, route }) => {
                  const href = base + route
                  const current = window.location.pathname === href
                  return <a key={href} className={`nav-item ${current ? "active" : ""}`} href={href}
                    aria-current={current ? "page" : undefined} aria-label={title} title={collapsed ? title : undefined}>
                    <Icon size={16} strokeWidth={1.8} />{!collapsed && <span>{title}</span>}
                  </a>
                })}
              </div>
            </div>
          })}
        </nav>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">
            <button type="button" className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Alternar menú" aria-expanded={mobileOpen} aria-controls="main-sidebar"><Menu size={18} /></button>
            <span>{account.company_name ?? "Administración SaaS"}</span><ChevronRight size={13} aria-hidden="true" /><b>{title}</b>
          </div>
          <details className="account-menu">
            <summary aria-label="Menú de usuario"><User size={15} /><span>{account.name}</span><ChevronDown size={13} /></summary>
            <div className="account-popover">
              <a href={base + "/profile"}><User size={15} />Perfil</a>
              <a href={base + "/preferences"}><SlidersHorizontal size={15} />Preferencias</a>
              <a href={base + "/password"}><KeyRound size={15} />Cambiar contraseña</a>
              <button onClick={logout} disabled={signingOut}><LogOut size={15} />Cerrar sesión</button>
              {error && <p className="form-error" role="alert">{error}</p>}
            </div>
          </details>
        </header>
        <section className="page-content">{children}</section>
      </main>
    </div>
  )
}
