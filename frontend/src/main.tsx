import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { AccessApp } from "./auth/AccessApp"
import "./styles.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode><AccessApp /></StrictMode>,
)
