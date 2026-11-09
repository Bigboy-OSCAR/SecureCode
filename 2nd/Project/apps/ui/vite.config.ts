/** Vite configuration for the same-origin local UI development server. */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { createViteApiProxy } from "../../scripts/dev/viteProxy.js";

export default defineConfig({
    plugins: [react()],
    server: {
        proxy: createViteApiProxy(),
    },
});
