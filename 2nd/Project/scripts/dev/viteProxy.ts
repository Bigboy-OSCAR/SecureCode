/**
 * Vite dev-server proxy settings for the UI (1.1 imports this in vite.config.ts).
 * The browser talks only to the Vite origin; `/api` is forwarded to the host on
 * loopback with the Host header rewritten (changeOrigin) so the host's
 * DNS-rebinding guard accepts it, while the browser's Origin header stays the
 * UI dev origin that the host allows. The HttpOnly cookie (Path=/api) and SSE
 * therefore work same-origin; no token is ever placed in a URL or VITE_ variable.
 */
export interface ViteApiProxyEntry {
    target: string;
    changeOrigin: true;
    secure: false;
    ws: false;
}

export function createViteApiProxy(hostPort = Number(process.env.SECURECODE_HOST_PORT?.trim() || 8787)): {
    "/api": ViteApiProxyEntry;
} {
    if (!Number.isInteger(hostPort) || hostPort < 1 || hostPort > 65535) {
        throw new Error("SECURECODE_HOST_PORT must be an integer between 1 and 65535");
    }
    return { "/api": { target: `http://127.0.0.1:${hostPort}`, changeOrigin: true, secure: false, ws: false } };
}
