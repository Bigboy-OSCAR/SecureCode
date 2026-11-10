/**
 * POST/GET /api/v1/workspaces/:workspace_id/index (3.6): R0 index build and status through the
 * context-service. The index never carries source text; POST answers 202 with the current status.
 */
import { SCHEMA_REFS, type IndexRequest } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { readContractBody } from "../shared/requestBody.js";

export function registerIndexRoutes(router: Router, services: RouteServices): void {
    const start: RouteHandler = async ({ request, response, params }) => {
        const workspaceId = params.workspace_id ?? "";
        services.workspaces.get(workspaceId);
        await readContractBody<IndexRequest>(request, services.validator, SCHEMA_REFS.indexRequest);
        await services.serviceWorkspaces.ensure(workspaceId);
        sendJson(response, 202, await services.contextClient.workspaces.startIndex(workspaceId));
    };
    const status: RouteHandler = async ({ response, params }) => {
        const workspaceId = params.workspace_id ?? "";
        services.workspaces.get(workspaceId);
        await services.serviceWorkspaces.ensure(workspaceId);
        sendJson(response, 200, await services.contextClient.workspaces.indexStatus(workspaceId));
    };
    router.add("POST", "/api/v1/workspaces/:workspace_id/index", start);
    router.add("GET", "/api/v1/workspaces/:workspace_id/index", status);
}
