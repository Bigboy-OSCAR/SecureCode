/** Vite configuration for the same-origin local UI development server. */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/api/v1": {
                target: "http://127.0.0.1:8787",
                changeOrigin: false,
            },
        },
    },
});
