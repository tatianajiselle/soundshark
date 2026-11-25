import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { trackOutboundLinks } from "./analytics";
import "./styles.css";

performance.mark("explorer:start");
trackOutboundLinks();

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
