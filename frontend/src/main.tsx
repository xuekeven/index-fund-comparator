import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ComparisonDashboard } from "@/components/comparison-dashboard";
import "./styles.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element was not found");
}

createRoot(root).render(
  <StrictMode>
    <ComparisonDashboard />
  </StrictMode>,
);
