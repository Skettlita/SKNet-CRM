import { useState } from "react"
import { PageHeading } from "../auth/AccessManagement"
import { api } from "../auth/api"
import type { Account } from "../auth/api"
import { ActionForm, Field } from "../auth/forms"
import { Button } from "../shared/Button"
import { DataTable, DataView, Panel, Pagination, Search, Select, Status, TextArea, optionalValue, searchPath, textValue, useData, usePager } from "../platform/shared"
import type { Page } from "../platform/shared"
import { Relation, allowed, appPath, asText, deviceCategories, useOptions } from "./model"
import type { Entry } from "./model"

export const inventory = "/inventory"
type Section = "types" | "manufacturers" | "models"
type Labelled = { id: string; name: string; active: boolean; type_id?: string; manufacturer_id?: string; type_name?: string; manufacturer_name?: string }
export type Stock = { id: string; model_id: string | null; type_id: string; manufacturer_id: string | null; model_name: string | null
  type_name: string; manufacturer_name: string | null; total: number; available: number; assigned: number; installed: number; maintenance: number; retired: number }

const sections: Record<Section, string> = { types: "Tipos", manufacturers: "Fabricantes", models: "Modelos" }

export function useCatalog(section: Section, enabled = true) {
  return useOptions<Labelled>(enabled ? inventory + "/catalog/" + section + "?only_active=true" : null)
}

function Choices({ items, label, name, value, change, required, known }: {
  items: Labelled[]; label: string; name: string; value: string; change: (id: string) => void; required?: boolean; known?: string
}) {
  return <Select label={label} name={name} value={value} required={required} onChange={(e) => change(e.target.value)}>
    <option value="">{required ? "Selecciona…" : "Sin definir"}</option>
    {value && !items.some((item) => item.id === value) && <option value={value}>{known || "Registro actual"}</option>}
    {items.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
  </Select>
}

export function CatalogFields({ account, entry, requireModel = false }: { account: Account; entry?: Entry; requireModel?: boolean }) {
  const enabled = allowed(account, "inventory.read")
  const types = useCatalog("types", enabled)
  const makers = useCatalog("manufacturers", enabled)
  const models = useCatalog("models", enabled)
  const [type, setType] = useState(asText(entry, "type_id"))
  const [maker, setMaker] = useState(asText(entry, "manufacturer_id"))
  const [model, setModel] = useState(asText(entry, "model_id"))
  const eligibleTypes = requireModel ? types.items.filter((item) => models.items.some((model) => model.type_id === item.id)) : types.items
  const eligibleMakers = requireModel
    ? makers.items.filter((item) => models.items.some((model) => model.type_id === type && model.manufacturer_id === item.id))
    : makers.items
  const options = models.items.filter((item) => item.type_id === type && item.manufacturer_id === maker)
  return <div className="form-grid">
    <Choices items={eligibleTypes} label="Tipo de dispositivo" name="type_id" required value={type} known={asText(entry, "catalog_type")}
      change={(value) => { setType(value); setModel(""); if (requireModel) setMaker("") }} />
    <Choices items={eligibleMakers} label="Fabricante" name="manufacturer_id" required={requireModel} value={maker} known={asText(entry, "catalog_manufacturer")}
      change={(value) => { setMaker(value); setModel("") }} />
    {(requireModel || (maker && type)) && <Choices items={options} label="Modelo" name="model_id" required={requireModel}
      value={model} known={asText(entry, "catalog_model")} change={setModel} />}
    {!enabled && !entry && <p className="description">Se requiere permiso para consultar el catálogo de equipos.</p>}
    {(types.error || makers.error || models.error) && <p className="form-error">{types.error || makers.error || models.error}</p>}
  </div>
}

export function AvailableModels({ category = "CUSTOMER_EQUIPMENT", name = "model_id", required }: {
  category?: string; name?: string; required?: boolean
}) {
  const data = useOptions<Stock>(inventory + "/stock?available=true&category=" + encodeURIComponent(category))
  return <>
    <Select label="Modelo disponible" name={name} required={required}>
      <option value="">Selecciona…</option>{data.items.map((item) => item.model_id && <option key={item.id} value={item.model_id}>
        {item.manufacturer_name} {item.model_name} · {item.available} disponibles
      </option>)}
    </Select>
    {data.error && <p className="form-error">{data.error}</p>}
  </>
}

export function StockPicker({ account, category }: { account: Account; category: string }) {
  const canPickModel = allowed(account, "inventory.read")
  const [mode, setMode] = useState(canPickModel ? "model" : "unit")
  const [unit, setUnit] = useState("")
  return <>
    {canPickModel && <Select label="Seleccionar por" value={mode} onChange={(event) => setMode(event.target.value)}>
      <option value="model">Modelo disponible</option><option value="unit">Unidad específica</option>
    </Select>}
    {mode === "model" ? <AvailableModels category={category} required />
      : <Relation kind="devices" name="device_id" label="Unidad disponible" value={unit} account={account} required
        filters={{ assignment_state: "AVAILABLE", device_category: category, status: "ACTIVE" }} change={setUnit} />}
  </>
}

export function InventoryCatalogs({ account }: { account: Account }) {
  const [section, setSection] = useState<Section>("types")
  const [editor, setEditor] = useState<Labelled | "new" | null>(null)
  const [deleting, setDeleting] = useState<Labelled | null>(null)
  const [q, setQuery] = useState("")
  const pager = usePager()
  const types = useCatalog("types", section === "models" && !!editor)
  const makers = useCatalog("manufacturers", section === "models" && !!editor)
  const path = inventory + "/catalog/" + section
  const state = useData<Page<Labelled>>("isp", searchPath(path, pager.offset, { q }), pager.version)
  const canEdit = allowed(account, "inventory.write")
  const record = editor === "new" ? undefined : editor ?? undefined
  return <><PageHeading title="Catálogos de equipos" action={canEdit && <Button variant="primary" onClick={() => setEditor("new")}>Registrar</Button>} />
    <div className="crm-tabs" aria-label="Catálogos">
      {(Object.entries(sections) as [Section, string][]).map(([value, label]) => <button key={value} type="button"
        aria-pressed={section === value} onClick={() => { setSection(value); setQuery(""); setEditor(null); setDeleting(null); pager.setOffset(0) }}>
        {label}
      </button>)}
    </div>
    {editor && <Panel title={record ? "Editar registro" : "Registrar en catálogo"}><div className="panel-body">
      <ActionForm key={record?.id ?? "new"} label="Guardar" cancel={() => setEditor(null)} submit={async (fields) => {
        await api("isp", path + (record ? "/" + record.id : ""), record ? "PUT" : "POST", {
          name: textValue(fields, "name"), active: fields.has("active"),
          ...(section === "models" ? { type_id: optionalValue(fields, "type_id"), manufacturer_id: optionalValue(fields, "manufacturer_id") } : {}),
        })
        setEditor(null)
        pager.reload()
      }}>
        <div className="form-grid">
          <Field label="Nombre" name="name" required maxLength={120} defaultValue={record?.name} />
          {section === "models" && <>
            <Select label="Tipo" name="type_id" defaultValue={record?.type_id ?? ""} required><option value="">Selecciona…</option>
              {record?.type_id && !types.items.some(({ id }) => id === record.type_id) && <option value={record.type_id}>{record.type_name}</option>}
              {types.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
            <Select label="Fabricante" name="manufacturer_id" defaultValue={record?.manufacturer_id ?? ""} required><option value="">Selecciona…</option>
              {record?.manufacturer_id && !makers.items.some(({ id }) => id === record.manufacturer_id) && <option value={record.manufacturer_id}>{record.manufacturer_name}</option>}
              {makers.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
          </>}
        </div>
        <label className="checkbox-label"><input type="checkbox" name="active" defaultChecked={record?.active ?? true} /> Activo</label>
      </ActionForm>
    </div></Panel>}
    {deleting && <Panel title={"Eliminar " + deleting.name}><div className="panel-body">
      <ActionForm label="Confirmar eliminación" cancel={() => setDeleting(null)} submit={async () => {
        await api("isp", path + "/" + deleting.id, "DELETE")
        setDeleting(null)
        pager.reload()
      }}><p>Confirma la eliminación del registro del catálogo.</p></ActionForm>
    </div></Panel>}
    <Panel>
      <div className="table-controls"><Search label="Buscar en catálogo" value={q} onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} /></div>
      <DataView state={state}>{({ items, has_more }) => <>
        <DataTable headers={["Nombre", ...(section === "models" ? ["Tipo", "Fabricante"] : []), "Estado", ...(canEdit ? ["Acciones"] : [])]}
          empty={items.length ? undefined : "No hay registros. Agrega los catálogos necesarios antes de registrar equipos."}>
          {items.map((item) => <tr key={item.id}><td>{item.name}</td>
            {section === "models" && <><td>{item.type_name}</td><td>{item.manufacturer_name}</td></>}
            <td><Status value={item.active ? "ACTIVE" : "INACTIVE"} /></td>
            {canEdit && <td className="row-actions"><Button onClick={() => setEditor(item)}>Editar</Button>
              <Button onClick={() => setDeleting(item)}>Eliminar</Button></td>}
          </tr>)}
        </DataTable><Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
  </>
}

function Units({ group, account }: { group: Stock; account: Account }) {
  const pager = usePager()
  const filters: Record<string, string> = group.model_id ? { model_id: group.model_id } : {
    type_id: group.type_id, manufacturer_id: group.manufacturer_id ?? "", old_model: group.model_name ?? "",
  }
  const state = useData<Page<Entry>>("isp", searchPath(inventory + "/stock/units", pager.offset, filters))
  return <Panel title={[group.manufacturer_name, group.model_name || group.type_name].filter(Boolean).join(" ")}><DataView state={state}>
    {({ items, has_more }) => <><DataTable headers={["Código", "Equipo", "Situación", "Serie", "MAC"]} empty={items.length ? undefined : "No hay unidades."}>
      {items.map((item) => <tr key={item.id}><td>{allowed(account, "devices.read") ? <a className="platform-link" href={appPath("devices", item.id)}>{item.device_code}</a> : item.device_code}</td>
        <td>{item.name}</td><td><Status value={asText(item, "assignment_state")} /></td><td>{item.serial_number || "—"}</td><td>{item.mac_address || "—"}</td>
      </tr>)}
    </DataTable><Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} /></>}
  </DataView></Panel>
}

export function InventoryStock({ account }: { account: Account }) {
  const pager = usePager()
  const [batch, setBatch] = useState(false)
  const [group, setGroup] = useState<Stock | null>(null)
  const [q, setQuery] = useState("")
  const [saved, setSaved] = useState(0)
  const state = useData<Page<Stock>>("isp", searchPath(inventory + "/stock", pager.offset, { q }), pager.version)
  return <><PageHeading title="Stock de equipos" action={allowed(account, "inventory.write") &&
    <Button variant="primary" onClick={() => { setSaved(0); setBatch(true) }}>Registrar lote</Button>} />
    {saved > 0 && <p className="panel-message" role="status">{saved} unidades registradas.</p>}
    {batch && <Panel title="Registrar lote"><div className="panel-body"><ActionForm label="Guardar lote" cancel={() => setBatch(false)}
      submit={async (fields) => {
        const result = await api<{ items: Entry[] }>("isp", inventory + "/stock/batches", "POST", {
          model_id: textValue(fields, "model_id"), quantity: Number(textValue(fields, "quantity")),
          device_category: textValue(fields, "device_category"), ownership: textValue(fields, "ownership"),
          description: optionalValue(fields, "description"),
        })
        setSaved(result.items.length)
        setBatch(false)
        pager.reload()
      }}>
      <CatalogFields account={account} requireModel />
      <div className="form-grid">
        <Select name="device_category" label="Categoría funcional" required><option value="">Selecciona…</option>
          {deviceCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        <Field label="Cantidad" name="quantity" type="number" defaultValue={1} min={1} max={200} required />
        <Select name="ownership" label="Propiedad" defaultValue="ISP">
          <option value="ISP">ISP</option><option value="CUSTOMER">Abonado</option><option value="THIRD_PARTY">Tercero</option><option value="UNKNOWN">Sin definir</option>
        </Select>
      </div>
      <TextArea label="Observaciones" name="description" maxLength={4000} />
    </ActionForm></div></Panel>}
    <Panel><div className="table-controls"><Search label="Buscar modelo, fabricante o tipo" value={q}
      onChange={(event) => { setQuery(event.target.value); pager.setOffset(0) }} /></div>
      <DataView state={state}>{({ items, has_more }) => <>
        <DataTable headers={["Tipo", "Fabricante", "Modelo", "Total", "Disponibles", "Asignados", "Instalados", "Mantenimiento", "Retirados"]}
          empty={items.length ? undefined : "Todavía no hay unidades."}>
          {items.map((item) => <tr key={item.id}><td>{item.type_name}</td><td>{item.manufacturer_name || "—"}</td>
            <td><Button onClick={() => setGroup(item)}>{item.model_name || "Unidades sin modelo"}</Button></td>
            {[item.total,item.available,item.assigned,item.installed,item.maintenance,item.retired].map((count, index) => <td key={index}>{count}</td>)}
          </tr>)}
        </DataTable><Pagination offset={pager.offset} more={has_more} onChange={pager.setOffset} />
      </>}</DataView>
    </Panel>
    {group && <Units key={group.id} group={group} account={account} />}
  </>
}
