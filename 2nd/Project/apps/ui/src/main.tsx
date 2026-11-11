/** Browser entry point for the SecureCode UI. */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App.js";
import "./styles/global.css";
import "./styles/components.css";
import "./app/app.css";
import "./features/features.css";
import "./styles/deskChat.css";
import "./styles/deskPanels.css";
import "./styles/deskDialogs.css";
import "./styles/deskAnswers.css";
import "./styles/deskApproval.css";
import "./styles/deskActivity.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
    throw new Error("The UI root element is missing.");
}

createRoot(rootElement).render(
    <StrictMode>
        <App />
    </StrictMode>,
);
