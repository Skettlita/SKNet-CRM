import { useState } from "react"

import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { ActionForm, Field } from "../auth/forms"
import { Select, optionalValue, textValue } from "../platform/shared"
import { Fields, Relation, allowed, asText, catalogs, crm, payload, siteTypesByCategory } from "./model"
import type { Entry } from "./model"
import { StockPicker } from "./Inventory"

export function serviceInput(fields: FormData) {
  const input = payload(catalogs.services.fields, fields)
  return { ...input, plan_id: textValue(fields, "plan_id"), access_router_id: optionalValue(fields, "access_router_id") }
}

export function ServiceFields({ account, entry }: { account: Account; entry?: Entry }) {
  const [plan, setPlan] = useState(asText(entry, "plan_id"))
  const [router, setRouter] = useState(asText(entry, "access_router_id"))
  const [access, setAccess] = useState(asText(entry, "access_method"))
  const [price, setPrice] = useState(asText(entry, "monthly_price"))
  const [currency, setCurrency] = useState(asText(entry, "currency"))
  const fields = catalogs.services.fields
    .filter(({ key }) => (key !== "pppoe_username" || access === "PPPOE") && (key !== "ip_assignment" || access !== "STATIC"))
  return <>
    <div className="form-grid crm-relations">
      <Relation kind="internet-plans" label="Plan de Internet" name="plan_id" value={plan} known={asText(entry, "plan_name")}
        account={account} required filters={{ status: "ACTIVE" }} change={(id, record) => {
          setPlan(id)
          setPrice(asText(record, "monthly_price"))
          setCurrency(asText(record, "currency"))
        }} />
      {access && allowed(account, "devices.read") && <Relation key={access} kind="devices" label="Router de acceso"
        name="access_router_id" value={router} known={asText(entry, "access_router_name")}
        account={account} filters={{ eligible_for: access }} change={setRouter} />}
      {access && !allowed(account, "devices.read") && router && <input type="hidden" name="access_router_id" value={router} />}
    </div>
    <Fields fields={fields} row={entry} values={{ access_method: access, monthly_price: price, currency }}
      onChange={(key, value) => {
        if (key === "access_method") { setAccess(value); setRouter("") }
        if (key === "monthly_price") setPrice(value)
        if (key === "currency") setCurrency(value)
      }} />
    <p className="description">Puedes ajustar el precio y la moneda del plan. La IP del servicio es independiente de la IP de gestión del equipo.</p>
  </>
}

export function SiteFields({ entry, category, siteType, sameAddress, requireAddress, changeType, prefix }: {
  entry?: Entry; category: string; siteType: string; sameAddress: boolean; requireAddress?: boolean
  changeType: (value: string) => void; prefix?: string
}) {
  const fields = catalogs.sites.fields
    .filter(({ key }) => !sameAddress || !["address", "city", ...(prefix ? ["name"] : [])].includes(key))
    .map((field) => {
      if (field.key === "site_type") return { ...field, options: siteTypesByCategory[category] ?? [] }
      if (field.key === "address") return { ...field, label: "Dirección del sitio", required: requireAddress }
      if (field.key === "city") return { ...field, label: "Ciudad del sitio" }
      return field
    })
  return <Fields fields={fields} row={entry} values={{ site_type: siteType }} prefix={prefix}
    onChange={(key, value) => { if (key === "site_type") changeType(value) }} />
}

export function CustomerRegistration({ account, cancel, complete }: {
  account: Account; cancel: () => void; complete: (entry: Entry) => void
}) {
  const [addService, setAddService] = useState(false)
  const [sameAddress, setSameAddress] = useState(false)
  const [siteType, setSiteType] = useState("")
  const [assign, setAssign] = useState(false)
  const canAssign = allowed(account, "inventory.read") && allowed(account, "devices.write")
  const canAddService = ["sites.create", "services.create", "internet_plans.read"].every((permission) => allowed(account, permission))
  return <ActionForm label="Guardar cliente" cancel={cancel} submit={async (fields) => {
    const address = optionalValue(fields, "customer_address")
    const customer = payload(catalogs.clients.fields, fields)
    const result = await api<{ client: Entry }>("isp", crm + "/clients/register", "POST", {
      ...customer,
      address: address ? { address, city: optionalValue(fields, "customer_city") } : null,
      ...(addService ? {
        service: serviceInput(fields),
        site: { ...payload(catalogs.sites.fields, fields, "initial_"), name: sameAddress ? null : textValue(fields, "initial_name"),
          use_client_address: sameAddress },
        initial_status: textValue(fields, "initial_status") || "PENDING",
        ...(assign ? { equipment: { model_id: optionalValue(fields, "model_id"), device_id: optionalValue(fields, "device_id") } } : {}),
      } : {}),
    })
    complete(result.client)
  }}>
    <section aria-labelledby="registration-customer" className="crm-form-section">
      <h3 id="registration-customer">Datos del cliente</h3>
      <Fields fields={catalogs.clients.fields} />
      <div className="form-grid">
        <Field label="Dirección del cliente" name="customer_address" minLength={2} maxLength={400} required={addService && sameAddress} />
        <Field label="Ciudad del cliente" name="customer_city" maxLength={120} />
      </div>
    </section>
    {canAddService && <label className="checkbox-label"><input type="checkbox" checked={addService}
      onChange={(event) => setAddService(event.target.checked)} /> Registrar un servicio contratado</label>}
    {addService && <>
      <section aria-labelledby="registration-service" className="crm-form-section">
        <h3 id="registration-service">Servicio contratado</h3>
        <ServiceFields account={account} />
        <InitialServiceStatus account={account} />
      </section>
      {canAssign && <section className="crm-form-section">
        <label className="checkbox-label"><input type="checkbox" checked={assign} onChange={(event) => setAssign(event.target.checked)} />
          Asignar equipamiento del cliente</label>
        {assign && <StockPicker account={account} category="CUSTOMER_EQUIPMENT" />}
      </section>}
      <section aria-labelledby="registration-site" className="crm-form-section">
        <h3 id="registration-site">Sitio del servicio</h3>
        <label className="checkbox-label"><input type="checkbox" checked={sameAddress}
          onChange={(event) => setSameAddress(event.target.checked)} /> Usar la dirección del cliente</label>
        <SiteFields category="CUSTOMER" siteType={siteType} sameAddress={sameAddress} requireAddress changeType={setSiteType} prefix="initial_" />
      </section>
    </>}
  </ActionForm>
}

export function InitialServiceStatus({ account }: { account: Account }) {
  return allowed(account, "services.status") ? <Select label="Estado inicial del servicio" name="initial_status" defaultValue="PENDING">
    <option value="PENDING">Pendiente</option><option value="ACTIVE">Activo</option>
  </Select> : null
}
