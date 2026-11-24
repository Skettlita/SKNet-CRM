import { useEffect, useState } from "react"
import type { ReactNode } from "react"

import { Brand } from "../shared/AppShell"
import { api, homePath, loginPath } from "./api"
import type { Scope } from "./api"
import { ActionForm, Field, PasswordFields, RegistrationFields } from "./forms"

function AccessCard({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return <main className="access-page">
    <section className="access-card">
      <div className="access-brand"><Brand /></div>
      <h1>{title}</h1>
      {description && <p className="description">{description}</p>}
      {children}
    </section>
  </main>
}

export function LoginPage({ scope }: { scope: Scope }) {
  const [signup, setSignup] = useState(false)
  useEffect(() => {
    if (scope === "isp") api<{ enabled: boolean }>("isp", "/signup").then((result) => setSignup(result.enabled)).catch(() => {})
  }, [scope])

  return <AccessCard title="Iniciar sesión" description={scope === "admin" ? "Administración SaaS de SKNet" : "Acceso para empresas proveedoras de Internet"}>
    <ActionForm label="Ingresar" submit={async (fields) => {
      await api(scope, "/login", "POST", Object.fromEntries(fields))
      window.location.replace(homePath(scope))
    }}>
      <Field label="Usuario o correo" name="identifier" autoComplete="username" maxLength={254} required />
      <Field label="Contraseña" name="password" type="password" autoComplete="current-password" maxLength={128} required />
    </ActionForm>
    <div className="access-links">
      <a href={scope === "admin" ? "/admin/recover" : "/recover"}>¿Olvidaste tu contraseña?</a>
      {signup && <a href="/signup">Registrar empresa</a>}
    </div>
  </AccessCard>
}

export function SignupPage() {
  const [available, setAvailable] = useState<boolean | null>(null)
  const [error, setError] = useState(false)
  const [complete, setComplete] = useState(false)
  useEffect(() => {
    api<{ enabled: boolean }>("isp", "/signup").then((result) => setAvailable(result.enabled)).catch(() => setError(true))
  }, [])

  return <AccessCard title="Registrar empresa" description="Crea la cuenta del administrador de tu empresa.">
    {error ? <p className="form-error" role="alert">No se pudo consultar la disponibilidad del registro.</p>
      : available === null ? <p role="status">Comprobando disponibilidad…</p>
      : complete ? <p role="status">Empresa registrada. Ya puedes iniciar sesión.</p>
      : !available ? <p role="status">El registro público está deshabilitado.</p>
      : <ActionForm label="Registrar empresa" submit={async (fields) => {
          await api("isp", "/signup", "POST", { ...Object.fromEntries(fields), accept_terms: fields.has("accept_terms") })
          setComplete(true)
        }}>
          <RegistrationFields />
          <details className="registration-terms">
            <summary>Condiciones de registro</summary>
            <p>Declaro que puedo registrar a la empresa y que los datos aportados son correctos. La cuenta se crea con el plan de prueba configurado en SKNet. La empresa administra el acceso de su personal.</p>
          </details>
          <label className="checkbox-label"><input type="checkbox" name="accept_terms" required /> Acepto las condiciones de registro.</label>
        </ActionForm>}
    <div className="access-links"><a href="/login">Volver al inicio de sesión</a></div>
  </AccessCard>
}

const recoveryParameters = new URLSearchParams(window.location.hash.slice(1))
const recoveryToken = recoveryParameters.get("token")
const verification = recoveryParameters.get("purpose") === "verify"
if (["/recover", "/admin/recover"].includes(window.location.pathname) && recoveryToken) {
  window.history.replaceState(null, "", window.location.pathname)
}

export function RecoverPage({ scope }: { scope: Scope }) {
  const [available, setAvailable] = useState<boolean | null>(scope === "admin" || recoveryToken ? true : null)
  const [error, setError] = useState(false)
  const [complete, setComplete] = useState(false)
  const token = scope === "isp" || verification ? recoveryToken : null

  useEffect(() => {
    if (scope === "isp" && !token) {
      api<{ email_enabled: boolean }>("isp", "/recover")
        .then((result) => setAvailable(result.email_enabled))
        .catch(() => setError(true))
    }
  }, [scope, token])

  return <AccessCard title={token && verification ? "Confirmar correo" : "Recuperar acceso"}>
    {scope === "admin" && !token ? <p>Solicita la recuperación al operador de SKNet. El acceso administrativo se recupera desde la terminal.</p>
      : error ? <p className="form-error" role="alert">No se pudo consultar el método de recuperación.</p>
      : available === null ? <p role="status">Comprobando…</p>
      : complete ? <p role="status">{token ? (verification ? "Correo confirmado." : "Contraseña actualizada. Ya puedes iniciar sesión.")
        : "Si hay una cuenta activa con ese correo, recibirás instrucciones."}</p>
      : token ? <ActionForm label={verification ? "Confirmar correo" : "Guardar nueva contraseña"} submit={async (fields) => {
          await api(scope, verification ? "/verify" : "/recover/confirm", "POST", { ...Object.fromEntries(fields), token })
          setComplete(true)
        }}>{!verification && <PasswordFields />}</ActionForm>
      : available ? <ActionForm label="Solicitar recuperación" submit={async (fields) => {
          await api("isp", "/recover", "POST", Object.fromEntries(fields))
          setComplete(true)
        }}><Field label="Correo electrónico" name="email" type="email" autoComplete="email" required /></ActionForm>
      : <p>La recuperación por correo no está configurada. Solicita una contraseña temporal al administrador de tu empresa o recurre al soporte de SKNet si administras la empresa.</p>}
    <div className="access-links"><a href={loginPath(scope)}>Volver al inicio de sesión</a></div>
  </AccessCard>
}

export function ChangePasswordPage({ scope, required, complete }: { scope: Scope; required: boolean; complete: () => void }) {
  const form = <ActionForm label="Cambiar contraseña" submit={async (fields) => {
    await api(scope, "/password", "POST", Object.fromEntries(fields))
    complete()
  }}>
    <Field label={required ? "Contraseña temporal" : "Contraseña actual"} name="current_password" autoComplete="current-password" type="password" maxLength={128} required />
    <PasswordFields />
  </ActionForm>

  return required
    ? <AccessCard title="Cambia tu contraseña" description="Elige una contraseña nueva de al menos 12 caracteres.">{form}</AccessCard>
    : form
}
