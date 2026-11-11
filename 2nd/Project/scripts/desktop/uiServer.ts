/** Serves the built desktop UI and streams same-origin API/SSE requests to the private host. */
import { createServer, request as proxyRequest, type IncomingMessage, type ServerResponse } from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, resolve, sep } from "node:path";

const MIME: Record<string, string> = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".ico": "image/x-icon",
};

function proxy(req: IncomingMessage, res: ServerResponse, hostPort: number): void {
    const upstream = proxyRequest(
        {
            hostname: "127.0.0.1",
            port: hostPort,
            path: req.url,
            method: req.method,
            headers: { ...req.headers, host: `127.0.0.1:${hostPort}` },
        },
        (response) => {
            res.writeHead(response.statusCode ?? 502, response.headers);
            response.pipe(res);
        },
    );
    upstream.on("error", () => {
        if (!res.headersSent) res.writeHead(502, { "content-type": "application/json" });
        res.end('{"error":{"code":"SERVICE_UNAVAILABLE","message":"Local service unavailable"}}');
    });
    res.on("close", () => upstream.destroy());
    req.pipe(upstream);
}

export async function startDesktopUi(options: { uiPort: number; hostPort: number; directory: string }): Promise<{
    url: string;
    stop(): Promise<void>;
}> {
    const root = resolve(options.directory);
    if (!existsSync(join(root, "index.html"))) throw new Error("Built UI missing; run npm run build first.");
    const server = createServer((req, res) => {
        if (req.headers.host !== `127.0.0.1:${options.uiPort}`) {
            res.writeHead(403).end();
            return;
        }
        if (req.url?.startsWith("/api/")) {
            proxy(req, res, options.hostPort);
            return;
        }
        if (req.method !== "GET" && req.method !== "HEAD") {
            res.writeHead(405).end();
            return;
        }
        let pathname: string;
        try {
            pathname = decodeURIComponent(new URL(req.url ?? "/", "http://localhost").pathname);
        } catch {
            res.writeHead(400).end();
            return;
        }
        const file = resolve(root, `.${pathname === "/" ? "/index.html" : pathname}`);
        if (!file.startsWith(root + sep) || !existsSync(file) || !statSync(file).isFile()) {
            res.writeHead(404).end();
            return;
        }
        res.writeHead(200, {
            "content-type": MIME[extname(file)] ?? "application/octet-stream",
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
        });
        if (req.method === "HEAD") res.end();
        else createReadStream(file).pipe(res);
    });
    await new Promise<void>((done, reject) => {
        server.once("error", reject);
        server.listen(options.uiPort, "127.0.0.1", done);
    });
    return {
        url: `http://127.0.0.1:${options.uiPort}`,
        stop: () =>
            new Promise<void>((done, reject) => {
                server.close((error) => (error ? reject(error) : done()));
                server.closeAllConnections();
            }),
    };
}
