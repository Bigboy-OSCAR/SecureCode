/** Exercises the actual UI Vite config, including its host-port override and header forwarding. */
import assert from "node:assert/strict";
import { createServer as createHttpServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer as createViteServer } from "vite";

function listen(server: Server): Promise<number> {
    return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => resolve((server.address() as AddressInfo).port));
    });
}

test("UI Vite proxy rewrites Host but preserves browser Origin, cookies and SSE", async () => {
    const upstream = createHttpServer((request, response) => {
        if (request.url?.endsWith("/events")) {
            response.writeHead(200, { "content-type": "text/event-stream" });
            response.end('id: 1\ndata: {"type":"run.status_changed"}\n\n');
            return;
        }
        response.writeHead(200, {
            "content-type": "application/json",
            "set-cookie": "securecode=test; HttpOnly; SameSite=Strict; Path=/api",
        });
        response.end(
            JSON.stringify({
                host: request.headers.host,
                origin: request.headers.origin,
                cookie: request.headers.cookie,
            }),
        );
    });
    const port = await listen(upstream);
    const previousPort = process.env.SECURECODE_HOST_PORT;
    process.env.SECURECODE_HOST_PORT = String(port);
    let vite: Awaited<ReturnType<typeof createViteServer>> | undefined;
    try {
        vite = await createViteServer({
            root: fileURLToPath(new URL("..", import.meta.url)),
            configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
            logLevel: "silent",
            server: { host: "127.0.0.1", port: 0, strictPort: true, watch: null },
        });
        await vite.listen();
        const uiPort = (vite.httpServer!.address() as AddressInfo).port;
        const origin = `http://127.0.0.1:${uiPort}`;
        const response = await fetch(`${origin}/api/v1/auth/bootstrap`, {
            method: "POST",
            headers: { origin, cookie: "securecode=previous" },
        });
        assert.equal(response.status, 200);
        assert.deepEqual(await response.json(), {
            host: `127.0.0.1:${port}`,
            origin,
            cookie: "securecode=previous",
        });
        assert.match(response.headers.get("set-cookie") ?? "", /HttpOnly; SameSite=Strict; Path=\/api/);
        const stream = await fetch(`${origin}/api/v1/runs/test/events`, { headers: { origin } });
        assert.equal(stream.headers.get("content-type"), "text/event-stream");
        assert.match(await stream.text(), /id: 1\ndata: .*run.status_changed/);
    } finally {
        if (previousPort === undefined) delete process.env.SECURECODE_HOST_PORT;
        else process.env.SECURECODE_HOST_PORT = previousPort;
        await vite?.close();
        upstream.closeAllConnections();
        await new Promise<void>((resolve) => upstream.close(() => resolve()));
    }
});
