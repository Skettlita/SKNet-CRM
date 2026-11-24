import { Button as ButtonPrimitive } from "@base-ui/react/button"

type Props = Omit<ButtonPrimitive.Props, "className"> & {
  variant?: "primary" | "outline"
}

export function Button({ variant = "outline", ...props }: Props) {
  return <ButtonPrimitive data-slot="button" className={`button button-${variant}`} {...props} />
}
