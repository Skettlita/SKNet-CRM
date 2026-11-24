import { useEffect, useState } from "react"
import { KeyRound, Pencil, Plus } from "lucide-react"

import { Button } from "../shared/Button"
import { api, message } from "./api"
import type { Account, Scope } from "./api"
import { ActionForm, Field, IdentityFields } from "./forms"

type User = {
  id: string
  name: string
  username: string
  email: string
  active: boolean
  must_change_password: boolean
  role_ids?: string[]
  editable: boolean
  resettable: boolean
}

type Role = {
  id: string
  name: string
  description: string | null
  permissions: string[]
  assignable: boolean
  editable: boolean
}

type Permission = { code: string; description: string }
type RoleList = { items: Role[]; permissions: Permission[]; delegable: string[] }

export function PageHeading({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return <div className="page-heading">
    <div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {action}
  </div>
}

export function TemporaryPassword({ secret }: { secret: string }) {
  return <div className="temporary-password" role="status">
    <strong>Contraseña temporal</strong>
    <code>{secret}</code>
    <p>Compártela por un canal seguro. Es de un solo uso, vence en 24 horas y debe cambiarse al entrar.</p>
  </div>
}

export function UserManagement({ scope, account, changed }: { scope: Scope; account: Account; changed: () => void }) {
  const [users, setUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [selected, setSelected] = useState<User | "new" | null>(null)
  const [resetTarget, setResetTarget] = useState<User | null>(null)
  const [secret, setSecret] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [query, setQuery] = useState("")
  const [more, setMore] = useState(false)
  const [revision, setRevision] = useState(0)
  const canReadRoles = account.permissions.includes("roles.read")
  const canCreate = account.permissions.includes("users.write")
  const pageSize = 30

  useEffect(() => {
    let current = true
    setLoading(true)
    setError("")
    const params = new URLSearchParams({ offset: String(offset), q: query, limit: String(pageSize) })
    const roleRequest = canReadRoles ? api<RoleList>(scope, "/roles") : Promise.resolve({ items: [] })
    Promise.all([api<{ items: User[]; has_more: boolean }>(scope, `/users?${params}`), roleRequest])
      .then(([result, roleResult]) => {
        if (!current) return
        setUsers(result.items)
        setMore(result.has_more)
        setRoles(roleResult.items)
      })
      .catch((error) => { if (current) setError(message(error)) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [scope, offset, query, revision, canReadRoles])

  function select(value: User | "new") {
    setSecret("")
    setResetTarget(null)
    setSelected(value)
  }

  const roleNames = new Map(roles.map((role) => [role.id, role.name]))
  const editing = selected && selected !== "new" ? selected : undefined
  const canAssign = canReadRoles && editing?.id !== account.id
  const existingRoles = editing?.role_ids ?? []
  const choices = roles.filter((role) => role.assignable)
  const editableAssignments = canAssign && existingRoles.every((id) => choices.some((role) => role.id === id))

  return <>
    <PageHeading title="Usuarios" description={scope === "admin" ? "Cuentas del personal de SKNet." : "Cuentas de tu empresa."}
      action={canCreate && <Button variant="primary" onClick={() => select("new")}><Plus size={15} />Nuevo usuario</Button>} />

    {secret && <TemporaryPassword secret={secret} />}
    {selected && <section className="table-panel editor-panel" aria-labelledby="user-editor">
      <div className="panel-header"><h2 id="user-editor">{editing ? "Editar usuario" : "Nuevo usuario"}</h2></div>
      <div className="panel-body">
        <ActionForm key={editing?.id ?? "new"} label="Guardar" cancel={() => setSelected(null)} submit={async (fields) => {
          const payload = {
            name: fields.get("name"),
            username: fields.get("username"),
            email: fields.get("email"),
          }
          const roles = fields.getAll("role_ids")
          if (editing) {
            await api(scope, `/users/${editing.id}`, "PUT", {
              ...payload, active: editing.id === account.id || fields.has("active"),
              ...(editableAssignments ? { role_ids: roles } : {}),
            })
            if (editing.id === account.id) changed()
          } else {
            const result = await api<{ temporary_password: string }>(scope, "/users", "POST", { ...payload, role_ids: roles })
            setSecret(result.temporary_password)
          }
          setSelected(null)
          setRevision((value) => value + 1)
        }}>
          <div className="form-grid"><IdentityFields values={editing} /></div>
          {editableAssignments && choices.length > 0 && <div className="permission-group">
            <strong>Roles asignados</strong>
            {choices.map((role) => <label className="checkbox-label" key={role.id}>
              <input type="checkbox" name="role_ids" value={role.id} defaultChecked={existingRoles.includes(role.id)} />
              {role.name}
            </label>)}
          </div>}
          {editing && editing.id !== account.id && <label className="checkbox-label">
            <input type="checkbox" name="active" defaultChecked={editing.active} /> Cuenta activa
          </label>}
        </ActionForm>
      </div>
    </section>}

    {resetTarget && <section className="table-panel editor-panel">
      <div className="panel-header"><h2>Restablecer acceso de {resetTarget.name}</h2></div>
      <div className="panel-body">
        <p>Se cerrarán las sesiones activas de esta cuenta.</p>
        <ActionForm label="Generar contraseña temporal" cancel={() => setResetTarget(null)} submit={async () => {
          const result = await api<{ temporary_password: string }>(scope, `/users/${resetTarget.id}/reset`, "POST")
          setSecret(result.temporary_password)
          setResetTarget(null)
          setRevision((value) => value + 1)
        }} />
      </div>
    </section>}

    <section className="table-panel">
      <div className="table-controls"><Field label="Buscar usuarios" type="search" maxLength={120} value={query}
        onChange={(event) => { setQuery(event.target.value); setOffset(0) }} /></div>
      {error ? <p className="panel-message form-error" role="alert">{error}</p>
        : loading ? <p className="panel-message" role="status">Cargando usuarios…</p>
        : users.length === 0 ? <p className="panel-message">No se encontraron usuarios.</p>
        : <div className="table-scroll"><table className="device-table access-table">
          <thead><tr><th scope="col">Nombre</th><th scope="col">Usuario</th><th scope="col">Correo</th>
            {canReadRoles && <th scope="col">Roles</th>}<th scope="col">Estado</th>
            {users.some((user) => user.editable || user.resettable) && <th scope="col">Acciones</th>}
          </tr></thead>
          <tbody>{users.map((user) => <tr key={user.id}>
            <td>{user.name}</td><td>{user.username}</td><td>{user.email}</td>
            {canReadRoles && <td>{user.role_ids?.map((id) => roleNames.get(id)).filter(Boolean).join(", ") || "Sin roles"}</td>}
            <td><span className={`status status-${user.active ? "up" : "muted"}`}><i aria-hidden="true" />
              {user.active ? user.must_change_password ? "Contraseña temporal" : "Activo" : "Inactivo"}</span></td>
            {users.some((entry) => entry.editable || entry.resettable) && <td>
              <div className="row-actions">
                {user.editable && <Button onClick={() => select(user)}>
                  <Pencil size={13} />Editar<span className="sr-only"> a {user.name}</span>
                </Button>}
                {user.resettable && <Button onClick={() => { setSecret(""); setSelected(null); setResetTarget(user) }}>
                  <KeyRound size={13} />Restablecer<span className="sr-only"> acceso de {user.name}</span>
                </Button>}
              </div>
            </td>}
          </tr>)}</tbody>
        </table></div>}
      {(offset > 0 || more) && <div className="table-controls pagination-controls">
        <Button disabled={offset === 0 || loading} onClick={() => setOffset(offset - pageSize)}>Anterior</Button>
        <span>Página {offset / pageSize + 1}</span>
        <Button disabled={!more || loading} onClick={() => setOffset(offset + pageSize)}>Siguiente</Button>
      </div>}
    </section>
  </>
}

const modules: Record<string, string> = {
  dashboard: "Dashboard", users: "Usuarios", roles: "Roles y permisos", settings: "Configuración",
  system: "Estado del sistema", companies: "Empresas", support: "Soporte",
  plans: "Planes", subscriptions: "Suscripciones", audit: "Auditoría",
  clients: "Clientes", internet_plans: "Planes de Internet", services: "Servicios", sites: "Sitios",
  devices: "Dispositivos", icmp: "Configuración ICMP", infrastructure: "Infraestructura", crm_history: "Historial CRM", connectivity: "Conectividad",
}

function PermissionMatrix({ catalog, current, delegable, readOnly }: {
  catalog: Permission[]; current: string[]; delegable: string[]; readOnly: boolean
}) {
  const grouped = new Map<string, Permission[]>()
  for (const permission of catalog) {
    if (!current.includes(permission.code) && (readOnly || !delegable.includes(permission.code))) continue
    const group = permission.code.split(".")[0]
    grouped.set(group, [...(grouped.get(group) ?? []), permission])
  }
  return <div className="table-scroll">
    <table className="device-table access-table permission-table">
      <thead><tr><th scope="col">Módulo</th><th scope="col">Acción</th><th scope="col">Permitir</th></tr></thead>
      {[...grouped].map(([group, permissions]) => <tbody key={group}>
        {permissions.map((permission, index) => <tr key={permission.code}>
          {index === 0 && <th rowSpan={permissions.length} scope="rowgroup">{modules[group] ?? group}</th>}
          <td><label htmlFor={`perm-${permission.code}`}>{permission.description}</label></td>
          <td><input id={`perm-${permission.code}`} type="checkbox" name="permissions" value={permission.code}
            defaultChecked={current.includes(permission.code)} disabled={readOnly || !delegable.includes(permission.code)} /></td>
        </tr>)}
      </tbody>)}
    </table>
  </div>
}

export function RoleManagement({ scope, account, changed }: { scope: Scope; account: Account; changed: () => void }) {
  const [result, setResult] = useState<RoleList | null>(null)
  const [selected, setSelected] = useState<Role | "new" | null>(null)
  const [error, setError] = useState("")
  const [revision, setRevision] = useState(0)
  const editable = selected === "new" || Boolean(selected?.editable)
  const role = selected && selected !== "new" ? selected : null

  useEffect(() => {
    let current = true
    api<RoleList>(scope, "/roles").then((data) => {
      if (current) { setResult(data); setError("") }
    }).catch((error) => { if (current) setError(message(error)) })
    return () => { current = false }
  }, [scope, revision])

  return <>
    <PageHeading title="Roles y permisos" description="Asigna permisos por módulo y acción."
      action={account.permissions.includes("roles.write") && result &&
        <Button variant="primary" onClick={() => setSelected("new")}><Plus size={15} />Nuevo rol</Button>} />
    {selected && result && <section className="table-panel editor-panel" aria-labelledby="role-editor">
      <div className="panel-header"><h2 id="role-editor">{role ? role.name : "Nuevo rol"}</h2></div>
      <div className="panel-body" key={role?.id ?? "new"}>
        {editable ? <ActionForm label="Guardar rol" cancel={() => setSelected(null)} submit={async (fields) => {
          await api(scope, role ? `/roles/${role.id}` : "/roles", role ? "PUT" : "POST", {
            name: fields.get("name"), description: fields.get("description"), permissions: fields.getAll("permissions"),
          })
          setSelected(null)
          setRevision((value) => value + 1)
          changed()
        }}>
          <div className="form-grid">
            <Field label="Nombre del rol" name="name" defaultValue={role?.name} minLength={2} maxLength={120} required />
            <Field label="Descripción" name="description" defaultValue={role?.description ?? ""} maxLength={240} />
          </div>
          <PermissionMatrix catalog={result.permissions} current={role?.permissions ?? []} delegable={result.delegable} readOnly={false} />
        </ActionForm> : <>
          {role?.description && <p>{role.description}</p>}
          <PermissionMatrix catalog={result.permissions} current={role?.permissions ?? []} delegable={result.delegable} readOnly />
          <div className="form-actions"><Button onClick={() => setSelected(null)}>Cerrar</Button></div>
        </>}
      </div>
    </section>}
    <section className="table-panel">
      {error ? <p className="panel-message form-error" role="alert">{error}</p>
        : !result ? <p className="panel-message" role="status">Cargando roles…</p>
        : result.items.length === 0 ? <p className="panel-message">Todavía no hay roles.</p>
        : <div className="table-scroll"><table className="device-table access-table">
          <thead><tr><th scope="col">Rol</th><th scope="col">Descripción</th><th scope="col">Permisos</th><th scope="col">Acciones</th></tr></thead>
          <tbody>{result.items.map((role) => <tr key={role.id}>
            <td>{role.name}</td><td>{role.description || "—"}</td><td>{role.permissions.length}</td>
            <td><Button onClick={() => setSelected(role)}>{role.editable ? "Editar" : "Ver"}<span className="sr-only"> {role.name}</span></Button></td>
          </tr>)}</tbody>
        </table></div>}
    </section>
  </>
}
