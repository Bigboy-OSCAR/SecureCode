/**
 * HTTP server assembly: request id, origin guard, browser authentication,
 * routing and error mapping. Business logic lives in route handlers and
 * services; this file only wires them.
 */
import { randomBytes } from "node:crypto";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { ContextServiceError } from "../context-client/contextServiceError.js";
import type { Logger } from "../logging/logger.js";
import { registerApprovalRoutes } from "../routes/approvals/approvalRoutes.js";
import { createLaunchCodeRoute } from "../routes/auth/launchCodeRoute.js";
import { createBootstrapRoute } from "../routes/auth/bootstrapRoute.js";
import { createHealthRoute } from "../routes/health/healthRoute.js";
import { registerPendingRoutes } from "../routes/pendingRoutes.js";
import { registerWorkspaceRoutes } from "../routes/projects/workspaceRoutes.js";
import { sendError } from "../routes/responses.js";
import type { RouteServices } from "../routes/routeServices.js";
import { Router } from "../routes/router.js";
import { registerRunEventsRoute } from "../routes/runs/runEventsRoute.js";
import { registerRunRoutes } from "../routes/runs/runRoutes.js";
import { registerSessionRoutes } from "../routes/sessions/sessionRoutes.js";
import { registerModelRoutes } from "../routes/settings/modelRoutes.js";
import { createSettingsRoute } from "../routes/settings/settingsRoute.js";
import { RouteFailure } from "../routes/shared/routeFailure.js";
import { registerPreviewRoute } from "../routes/context/previewRoute.js";
import { registerPdfRoutes } from "../routes/pdf/pdfRoutes.js";
import { registerIndexRoutes } from "../routes/projects/indexRoutes.js";
import { registerPointerRoutes } from "../routes/pointers/pointerRoutes.js";
import { checkRequestOrigin, type OriginPolicy } from "../security/originGuard.js";

export interface HostServerDependencies {
    services: RouteServices;
    originPolicy: OriginPolicy;
    logger: Logger;
    providerConfigured: () => boolean;
}

const REQUEST_ID_PATTERN = /^req_[A-Za-z0-9-]{8,64}$/;
const PUBLIC_ROUTES = new Set(["GET /api/v1/health", "POST /api/v1/auth/bootstrap", "POST /api/v1/auth/launch-code"]);

function resolveRequestId(request: IncomingMessage): string {
    const incoming = request.headers["x-request-id"];
    if (typeof incoming === "string" && REQUEST_ID_PATTERN.test(incoming)) {
        return incoming;
    }
    return `req_${randomBytes(12).toString("hex")}`;
}

export function buildRouter(dependencies: HostServerDependencies): Router {
    const { services } = dependencies;
    const router = new Router()
        .add(
            "GET",
            "/api/v1/health",
            createHealthRoute({
                contextClient: services.contextClient,
                isAuthenticated: (cookie) => services.auth.isAuthenticated(cookie),
                providerConfigured: dependencies.providerConfigured,
            }),
        )
        .add("POST", "/api/v1/auth/bootstrap", createBootstrapRoute(services))
        .add("POST", "/api/v1/auth/launch-code", createLaunchCodeRoute(services))
        .add("GET", "/api/v1/settings", createSettingsRoute(services));
    registerModelRoutes(router, services);
    registerWorkspaceRoutes(router, services);
    registerSessionRoutes(router, services);
    registerRunRoutes(router, services);
    registerRunEventsRoute(router, services);
    registerApprovalRoutes(router, services);
    registerIndexRoutes(router, services);
    registerPointerRoutes(router, services);
    registerPreviewRoute(router, services);
    registerPdfRoutes(router, services);
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
    const method = (request.method ?? "GET").toUpperCase();

    const rejection = checkRequestOrigin({ method, headers: request.headers }, dependencies.originPolicy);
    if (rejection) {
        sendError(response, { code: rejection, message: "request origin is not allowed" }, requestId);
        return;
    }

    const path = (request.url ?? "/").split("?", 1)[0] ?? "/";
    const match = router.match(method, path);
    if (match.kind === "invalid_path") {
        sendError(response, { code: "VALIDATION_FAILED", message: "invalid request path" }, requestId);
        return;
    }
    if (match.kind !== "found") {
        sendError(response, { code: "NOT_FOUND", message: "route not found" }, requestId);
        return;
    }
    const routeKey = `${method} ${path.replace(/\/+$/, "")}`;
    if (!PUBLIC_ROUTES.has(routeKey) && !dependencies.services.auth.isAuthenticated(request.headers.cookie)) {
        sendError(response, { code: "UNAUTHENTICATED", message: "sign in with the launch code first" }, requestId);
        return;
    }
    try {
        await match.handler({ request, response, params: match.params, requestId });
    } catch (error) {
        if (response.headersSent) throw error;
        if (error instanceof RouteFailure) {
            sendError(response, error.error, requestId);
        } else if (error instanceof ContextServiceError) {
            sendError(
                response,
                {
                    code: error.code,
                    message: error.message,
                    retryable: error.retryable,
                    ...(error.details ? { details: error.details } : {}),
                },
                requestId,
            );
        } else {
            throw error;
        }
    }
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
