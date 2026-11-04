/**
 * HTTP server assembly: request id, origin guard, routing and error mapping.
 * Business logic lives in route handlers; this file only wires them.
 */
import { randomBytes } from "node:crypto";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { ContextServiceClient } from "../context-client/ports.js";
import type { Logger } from "../logging/logger.js";
import { createHealthRoute } from "../routes/health/healthRoute.js";
import { registerPendingRoutes } from "../routes/pendingRoutes.js";
import { sendError } from "../routes/responses.js";
import { Router } from "../routes/router.js";
import { checkRequestOrigin, type OriginPolicy } from "../security/originGuard.js";

export interface HostServerDependencies {
    contextClient: ContextServiceClient;
    originPolicy: OriginPolicy;
    logger: Logger;
}

const REQUEST_ID_PATTERN = /^req_[A-Za-z0-9-]{8,64}$/;

function resolveRequestId(request: IncomingMessage): string {
    const incoming = request.headers["x-request-id"];
    if (typeof incoming === "string" && REQUEST_ID_PATTERN.test(incoming)) {
        return incoming;
    }
    return `req_${randomBytes(12).toString("hex")}`;
}

export function buildRouter(dependencies: HostServerDependencies): Router {
    const router = new Router().add("GET", "/api/v1/health", createHealthRoute(dependencies.contextClient));
    registerPendingRoutes(router);
    return router;
}

async function handleRequest(
    router: Router,
    dependencies: HostServerDependencies,
    request: IncomingMessage,
    response: ServerResponse,
): Promise<void> {
    const requestId = resolveRequestId(request);
    response.setHeader("x-request-id", requestId);
    const path = new URL(request.url ?? "/", "http://127.0.0.1").pathname;

    const rejection = checkRequestOrigin(
        { method: request.method ?? "GET", headers: request.headers },
        dependencies.originPolicy,
    );
    if (rejection) {
        sendError(response, { code: rejection, message: "request origin is not allowed" }, requestId);
        return;
    }

    const match = router.match(request.method ?? "GET", path);
    if (match.kind !== "found") {
        sendError(response, { code: "NOT_FOUND", message: "route not found" }, requestId);
        return;
    }
    await match.handler({ request, response, params: match.params, requestId });
}

export function createHostServer(dependencies: HostServerDependencies): Server {
    const router = buildRouter(dependencies);
    return createServer((request, response) => {
        handleRequest(router, dependencies, request, response).catch((error: unknown) => {
            const requestId = String(response.getHeader("x-request-id") ?? "req_unassigned0");
            dependencies.logger.error(
                `unhandled ${error instanceof Error ? error.name : "error"} request_id=${requestId}`,
            );
            if (!response.headersSent) {
                sendError(response, { code: "INTERNAL_ERROR", message: "internal error" }, requestId);
            } else {
                response.destroy();
            }
        });
    });
}
