import { useEffect, useRef, useState } from "react"
import type { FormEvent, InputHTMLAttributes, ReactNode } from "react"

import { Button } from "../shared/Button"
import { ApiError, message } from "./api"
import { FormErrors, useFieldError } from "./formErrors"

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string }

export function Field({ label, ...input }: FieldProps) {
  const { error, id, attrs } = useFieldError(input.name)
  return <label className="form-field"><span>{label}</span><input {...input} {...attrs} />
    {error && <span id={id} className="form-error">{error}</span>}
  </label>
}

export function PasswordFields() {
  return <>
    <Field label="Contraseña" name="password" autoComplete="new-password" type="password" minLength={12} maxLength={128} required />
    <Field label="Confirmar contraseña" name="confirm_password" autoComplete="new-password" type="password" minLength={12} maxLength={128} required />
  </>
}

export function IdentityFields({ values }: { values?: { name: string; username: string; email: string } }) {
  return <>
    <Field label="Nombre completo" name="name" autoComplete="name" minLength={2} maxLength={120} defaultValue={values?.name} required />
    <Field label="Nombre de usuario" name="username" autoComplete="username" pattern={"[A-Za-z0-9_.\\-]{3,64}"} title="De 3 a 64 letras, números, puntos, guiones o guiones bajos" defaultValue={values?.username} required />
    <Field label="Correo electrónico" name="email" autoComplete="email" type="email" maxLength={254} defaultValue={values?.email} required />
  </>
}

export function RegistrationFields() {
  return <>
    <Field label="Empresa" name="company" autoComplete="organization" minLength={2} maxLength={120} required />
    <Field label="NIT (opcional)" name="tax_id" maxLength={40} />
    <Field label="Teléfono" name="phone" autoComplete="tel" type="tel" minLength={5} maxLength={30} required />
    <IdentityFields />
    <PasswordFields />
  </>
}

export function ActionForm({ children, submit, label, cancel }: {
  children?: ReactNode
  submit: (values: FormData) => Promise<void>
  label: string
  cancel?: () => void
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")
  const [fields, setFields] = useState<Record<string, string>>({})
  const form = useRef<HTMLFormElement>(null)
  useEffect(() => {
    const invalid = form.current?.querySelector<HTMLElement>("[aria-invalid=true]")
    invalid?.focus({ preventScroll: true })
    invalid?.scrollIntoView({ block: "nearest" })
  }, [fields])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    setError("")
    setFields({})
    setPending(true)
    try {
      await submit(new FormData(event.currentTarget))
    } catch (error) {
      setError(message(error))
      if (error instanceof ApiError) {
        const matched: Record<string, string> = {}
        const names = new Set(Array.from(form.current?.elements ?? [], (item) => item.getAttribute("name")))
        for (const [path, detail] of Object.entries(error.fields)) {
          const key = path.replace(/^site\./, "initial_").replace(/^address\./, "customer_").replace(/^service\./, "")
          const field = [key, path, key.split(".")[0]].find((candidate) => names.has(candidate))
          if (field) matched[field] = detail
        }
        setFields(matched)
      }
    } finally {
      setPending(false)
    }
  }

  return <form ref={form} className="action-form" onSubmit={onSubmit}>
    <fieldset disabled={pending}>
      <FormErrors.Provider value={fields}>{children}</FormErrors.Provider>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="form-actions">
        <Button type="submit" variant="primary">{pending ? "Procesando…" : label}</Button>
        {cancel && <Button type="button" onClick={cancel}>Cancelar</Button>}
      </div>
    </fieldset>
  </form>
}
