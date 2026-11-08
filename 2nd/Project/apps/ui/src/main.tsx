/** Browser entry point for the SecureCode UI. */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App.js";
import "./styles/global.css";
import "./styles/components.css";
import "./app/app.css";
import "./features/features.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
    throw new Error("The UI root element is missing.");
}

createRoot(rootElement).render(
    <StrictMode>
        <App />
    </StrictMode>,
);
