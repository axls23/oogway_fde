import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/theme.css";
import "./styles/global.css";

async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCKS === "true") {
    const { installMockApi } = await import("./mocks/server");
    installMockApi();
  }

  const rootEl = document.getElementById("root");
  if (!rootEl) throw new Error("#root element not found");

  createRoot(rootEl).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
