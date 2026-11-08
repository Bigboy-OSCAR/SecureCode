/**
 * Public /api/v1 routes from roadmap 0.6 that are contracted but not connected
 * yet (index, pointers, context preview, PDF: 3.6 assembles them). They answer
 * 501 NOT_IMPLEMENTED with the owning task instead of a fake success, behind the
 * same browser authentication as the implemented routes. Owners replace an
 * entry with the real handler when their task lands.
 */
import { sendError } from "./responses.js";
import type { Router } from "./router.js";

export interface PendingRoute {
    method: string;
    path: string;
    ownerTask: string;
}

export const PENDING_ROUTES: readonly PendingRoute[] = [
    { method: "POST", path: "/api/v1/workspaces/:workspace_id/index", ownerTask: "3.6" },
    { method: "GET", path: "/api/v1/workspaces/:workspace_id/index", ownerTask: "3.6" },
    { method: "GET", path: "/api/v1/workspaces/:workspace_id/pointers", ownerTask: "3.6" },
    { method: "POST", path: "/api/v1/workspaces/:workspace_id/sources", ownerTask: "3.6" },
    { method: "POST", path: "/api/v1/pointers/read", ownerTask: "3.6" },
    { method: "POST", path: "/api/v1/pointers/search", ownerTask: "3.6" },
    { method: "DELETE", path: "/api/v1/pointers", ownerTask: "3.6" },
    { method: "POST", path: "/api/v1/context/preview", ownerTask: "3.6" },
    { method: "POST", path: "/api/v1/pdf/parse", ownerTask: "3.6" },
    { method: "GET", path: "/api/v1/pdf/jobs/:job_id", ownerTask: "3.6" },
];

export function registerPendingRoutes(router: Router): void {
    for (const route of PENDING_ROUTES) {
        router.add(route.method, route.path, ({ response, requestId }) => {
            sendError(
                response,
                {
                    code: "NOT_IMPLEMENTED",
                    message: `${route.method} ${route.path} is not implemented yet`,
                    details: { owner_task: route.ownerTask },
                },
                requestId,
            );
            return Promise.resolve();
        });
    }
}
