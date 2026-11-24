export type Scope = "isp" | "admin"

export type Account = {
  id: string
  name: string
  username: string
  email: string
  company_id: string | null
  company_name: string | null
  email_verified: boolean
  email_verification_available: boolean
  compact_view: boolean
  must_change_password: boolean
  permissions: string[]
  plan: { code: string; version: number; current: boolean; access_enabled: boolean; max_users: number | null } | null
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export async function api<T>(scope: Scope, path: string, method = "GET", body?: object): Promise<T> {
  const response = await fetch(`/api/v1/${scope}${path}`, {
    method,
    cache: "no-store",
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, typeof data?.detail === "string" ? data.detail : "No se pudo completar la solicitud.")
  }
  return data as T
}

export const homePath = (scope: Scope) => scope === "admin" ? "/admin" : "/app"
export const loginPath = (scope: Scope) => scope === "admin" ? "/admin/login" : "/login"

export function message(error: unknown) {
  return error instanceof ApiError ? error.message : "No se pudo conectar con SKNet. Intenta de nuevo."
}
