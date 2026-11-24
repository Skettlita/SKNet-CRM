import { useEffect, useState } from "react"

import { Button } from "../shared/Button"
import { PageHeading, TemporaryPassword } from "./AccessManagement"
import { api, message } from "./api"
import type { Account, Scope } from "./api"
import { ActionForm, Field, RegistrationFields } from "./forms"
import { ChangePasswordPage } from "./PublicPages"

type Settings = {
  public_signup_enabled: boolean
  monthly_price: number
  trial_days: number | null
  max_users: number | null
  version: number
}

export function SettingsPage({ account }: { account: Account }) {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState(false)
  const editable = account.permissions.includes("settings.write")

  useEffect(() => {
    api<Settings>("admin", "/settings").then(setSettings).catch((error) => setError(message(error)))
  }, [])

  return <>
    <PageHeading title="Configuración" description="Registro público y condiciones del plan de prueba para nuevas empresas." />
    <section className="table-panel">
      <div className="panel-header"><h2>Plan de prueba</h2></div>
      <div className="panel-body">
        {error ? <p className="form-error" role="alert">{error}</p>
          : !settings ? <p role="status">Cargando configuración…</p>
          : editable ? <ActionForm label="Guardar configuración" submit={async (fields) => {
              setSaved(false)
              const trial = fields.get("trial_days")
              const limit = fields.get("max_users")
              const updated = await api<Settings>("admin", "/settings", "PUT", {
                public_signup_enabled: fields.has("public_signup_enabled"),
                monthly_price: fields.get("monthly_price"),
                trial_days: trial ? Number(trial) : null,
                max_users: limit ? Number(limit) : null,
              })
              setSettings(updated)
              setSaved(true)
            }}>
              <label className="checkbox-label"><input type="checkbox" name="public_signup_enabled"
                defaultChecked={settings.public_signup_enabled} /> Habilitar registro público ISP</label>
              <div className="form-grid">
                <Field label="Precio mensual (Bs)" name="monthly_price" type="number" min={0} step="0.01" defaultValue={settings.monthly_price} required />
                <Field label="Duración de prueba en días (opcional)" name="trial_days" type="number" min={1} max={3650} defaultValue={settings.trial_days ?? ""} />
                <Field label="Máximo de usuarios activos (opcional)" name="max_users" type="number" min={1} max={100000} defaultValue={settings.max_users ?? ""} />
              </div>
              <p className="description">Deja la duración o el máximo en blanco para un plan sin vencimiento o sin límite, respectivamente.</p>
              {saved && <p role="status" className="form-success">Configuración guardada. Versión del plan {settings.version}.</p>}
            </ActionForm> : <dl className="profile-details">
              <dt>Registro público</dt><dd>{settings.public_signup_enabled ? "Habilitado" : "Deshabilitado"}</dd>
              <dt>Precio mensual</dt><dd>Bs {settings.monthly_price}</dd>
              <dt>Duración</dt><dd>{settings.trial_days === null ? "Sin vencimiento" : `${settings.trial_days} días`}</dd>
              <dt>Usuarios activos</dt><dd>{settings.max_users ?? "Sin límite"}</dd>
            </dl>}
      </div>
    </section>
  </>
}

export function ManualRegistration() {
  const [completed, setCompleted] = useState(false)
  return <>
    <PageHeading title="Nueva empresa" description="Da de alta una empresa y su primer administrador ISP." />
    <section className="table-panel"><div className="panel-body">
      {completed ? <><p className="form-success" role="status">Empresa registrada.</p>
        <Button onClick={() => setCompleted(false)}>Registrar otra empresa</Button></>
        : <ActionForm label="Registrar empresa" submit={async (fields) => {
          await api("admin", "/companies", "POST", Object.fromEntries(fields))
          setCompleted(true)
        }}><div className="form-grid"><RegistrationFields /></div></ActionForm>}
    </div></section>
  </>
}

export function SupportResetPage() {
  const [secret, setSecret] = useState("")
  return <>
    <PageHeading title="Recuperar acceso ISP" description="Emite una contraseña temporal después de verificar la identidad del solicitante." />
    <section className="table-panel"><div className="panel-body">
      {secret ? <><TemporaryPassword secret={secret} /><Button onClick={() => setSecret("")}>Cerrar</Button></>
        : <ActionForm label="Generar contraseña temporal" submit={async (fields) => {
          const response = await api<{ temporary_password: string }>("admin", "/support/reset", "POST", {
            ...Object.fromEntries(fields), identity_verified: fields.has("identity_verified"),
          })
          setSecret(response.temporary_password)
        }}>
          <div className="form-grid">
            <Field label="Usuario o correo ISP" name="identifier" maxLength={254} required />
            <Field label="Motivo del restablecimiento" name="reason" maxLength={500} required />
          </div>
          <label className="checkbox-label"><input type="checkbox" name="identity_verified" required /> Verifiqué la identidad del solicitante.</label>
        </ActionForm>}
    </div></section>
  </>
}

export function ProfilePage({ scope, account, view, changed }: {
  scope: Scope; account: Account; view: "profile" | "preferences" | "password"; changed: () => void
}) {
  const [saved, setSaved] = useState(false)
  const [verificationRequested, setVerificationRequested] = useState(false)
  const title = view === "password" ? "Cambiar contraseña" : view === "preferences" ? "Preferencias" : "Perfil"
  return <>
    <PageHeading title={title} />
    <section className="table-panel"><div className="panel-body">
      {view === "password" ? <ChangePasswordPage scope={scope} required={false} complete={() => {
        setSaved(true)
        changed()
      }} /> : <ActionForm label="Guardar" submit={async (fields) => {
        await api(scope, "/profile", "PUT", {
          name: view === "profile" ? fields.get("name") : account.name,
          compact_view: view === "preferences" ? fields.has("compact_view") : account.compact_view,
        })
        setSaved(true)
        changed()
      }}>
        {view === "profile" ? <>
          <div className="form-grid"><Field label="Nombre completo" name="name" minLength={2} maxLength={120} defaultValue={account.name} required /></div>
          <dl className="profile-details"><dt>Usuario</dt><dd>{account.username}</dd><dt>Correo</dt><dd>{account.email}</dd></dl>
        </> : <label className="checkbox-label"><input type="checkbox" name="compact_view" defaultChecked={account.compact_view} /> Reducir altura de las filas</label>}
      </ActionForm>}
      {view === "profile" && account.email_verification_available && (
        account.email_verified ? <p role="status">Correo verificado.</p>
          : <ActionForm label="Enviar enlace de verificación" submit={async () => {
              await api(scope, "/profile/verify-email", "POST")
              setVerificationRequested(true)
            }}>
              {verificationRequested && <p role="status">Solicitud recibida. Revisa tu correo para confirmarlo.</p>}
            </ActionForm>
      )}
      {saved && <p role="status" className="form-success">Cambios guardados.</p>}
    </div></section>
  </>
}
