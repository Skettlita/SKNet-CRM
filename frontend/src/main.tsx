import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { FoundationDashboard } from "./FoundationDashboard"
import "./styles.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode><FoundationDashboard /></StrictMode>,
)
