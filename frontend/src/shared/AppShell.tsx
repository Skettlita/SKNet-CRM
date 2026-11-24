import { useState } from "react"
import type { ReactNode } from "react"
import { ChevronLeft, ChevronRight, LayoutDashboard, Menu, Network, X } from "lucide-react"

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

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="app-shell">
      <aside
        id="main-sidebar"
        className={`sidebar ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`}
        onKeyDown={(event) => { if (event.key === "Escape") setMobileOpen(false) }}
      >
        <div className="brand">
          <Brand compact={collapsed} />
          <button
            type="button"
            className="collapse-btn"
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Expandir menú" : "Contraer menú"}
            aria-expanded={!collapsed}
            aria-controls="main-navigation"
          >
            <ChevronLeft size={15} className={collapsed ? "rotate" : ""} />
          </button>
          <button type="button" className="mobile-menu" onClick={() => setMobileOpen(false)} aria-label="Cerrar menú">
            <X size={18} />
          </button>
        </div>
        <nav id="main-navigation" className="side-nav" aria-label="Navegación principal">
          <div className="nav-group">
            {!collapsed && <div className="nav-heading">GENERAL</div>}
            <a className="nav-item active" href="/" aria-current="page" aria-label="Dashboard" title={collapsed ? "Dashboard" : undefined}>
              <LayoutDashboard size={16} strokeWidth={1.8} />
              {!collapsed && <span>Dashboard</span>}
            </a>
          </div>
        </nav>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">
            <button type="button" className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Alternar menú" aria-expanded={mobileOpen} aria-controls="main-sidebar">
              <Menu size={18} />
            </button>
            <span>SKNet</span><ChevronRight size={13} aria-hidden="true" /><b>Dashboard</b>
          </div>
        </header>
        {children}
      </main>
    </div>
  )
}
