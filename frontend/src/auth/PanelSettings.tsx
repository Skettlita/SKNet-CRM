import { useState } from "react"

import { Button } from "../shared/Button"
import { PageHeading, TemporaryPassword } from "./AccessManagement"
import { api } from "./api"
import type { Account, Scope } from "./api"
import { ActionForm, Field, RegistrationFields } from "./forms"
import { ChangePasswordPage } from "./PublicPages"

import { DataView, Select, amountText, useData } from "../platform/shared"
import type { PlanChoice } from "../platform/shared"

type Settings = {
  id: string; name: string; public_signup_enabled: boolean; currency: string; billing_period: string
  monthly_price: number | string; trial_days: number | null; max_users: number | null; version: number
}

export function SettingsPage({ account }: { account: Account }) {
  const [updated, setUpdated] = useState<Settings>()
  const current = useData<Settings>("admin", "/settings")
  const editable = account.permissions.includes("settings.write")
  const options = useData<PlanChoice[]>("admin", editable ? "/plans/choices" : null)

  return <>
    <PageHeading title="Configuración" description="Registro público y plan predeterminado para las nuevas empresas." />
    <section className="table-panel">
      <div className="panel-header"><h2>Registro de empresas ISP</h2></div>
      <div className="panel-body">
        <DataView state={current}>{(loaded) => {
          const settings = updated ?? loaded
          return <>
            {editable && <DataView state={options}>{(plans) =>
              <ActionForm label="Guardar configuración" submit={async (fields) => {
                setUpdated(await api<Settings>("admin", "/settings", "PUT", {
                  public_signup_enabled: fields.has("public_signup_enabled"),
                  default_plan_version_id: fields.get("default_plan_version_id"),
                }))
              }}>
                <label className="checkbox-label"><input type="checkbox" name="public_signup_enabled"
                  defaultChecked={settings.public_signup_enabled} /> Habilitar registro público ISP</label>
                <div className="form-grid">
                  <Select label="Plan predeterminado" name="default_plan_version_id" defaultValue={settings.id} required>
                    {!plans.some((plan) => plan.version_id === settings.id) &&
                      <option disabled value={settings.id}>{settings.name} · v{settings.version} (desactivado)</option>}
                    {plans.map((plan) => <option key={plan.version_id} value={plan.version_id}>{plan.name} · v{plan.version}</option>)}
                  </Select>
                </div>
                {updated && <p role="status" className="form-success">Configuración guardada.</p>}
              </ActionForm>}
            </DataView>}
            <dl className="profile-details platform-summary">
              <dt>Registro público</dt><dd>{settings.public_signup_enabled ? "Habilitado" : "Deshabilitado"}</dd>
              <dt>Plan predeterminado</dt><dd>{settings.name} · v{settings.version}</dd>
              <dt>Precio</dt><dd>{amountText(settings.monthly_price, settings.currency)} · {settings.billing_period === "YEARLY" ? "Anual" : "Mensual"}</dd>
              <dt>Duración</dt><dd>{settings.trial_days === null ? "Sin vencimiento" : settings.trial_days + " días"}</dd>
              <dt>Usuarios activos</dt><dd>{settings.max_users ?? "Sin límite"}</dd>
            </dl>
          </>
        }}</DataView>
      </div>
    </section>
  </>
}

export function ManualRegistration({ account }: { account: Account }) {
  const [completed, setCompleted] = useState("")
  return <>
    {account.permissions.includes("companies.read") && <a className="platform-link back-link" href="/admin/companies">Volver a empresas</a>}
    <PageHeading title="Nueva empresa" description="Da de alta una empresa y su primer administrador ISP." />
    <section className="table-panel"><div className="panel-body">
      {completed ? <><p className="form-success" role="status">Empresa registrada.</p>
        <div className="row-actions"><Button onClick={() => setCompleted("")}>Registrar otra empresa</Button>{account.permissions.includes("companies.read") && <a className="button button-outline" href={"/admin/companies/" + completed}>Consultar empresa</a>}</div></>
        : <ActionForm label="Registrar empresa" submit={async (fields) => {
          const result = await api<{ company_id: string }>("admin", "/companies", "POST", Object.fromEntries(fields))
          setCompleted(result.company_id)
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
