import { createContext, useContext, useId } from "react"

export const FormErrors = createContext<Record<string, string>>({})

export function useFieldError(name?: string) {
  const errors = useContext(FormErrors)
  const error = name ? errors[name] : undefined
  const id = useId()
  return { error, id, attrs: error ? { "aria-invalid": true as const, "aria-describedby": id } : {} }
}
