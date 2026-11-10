/** Workspace routes: POST/GET /api/v1/workspaces and GET /api/v1/workspaces/:workspace_id. */
import { SCHEMA_REFS, type WorkspaceCreateRequest, type WorkspaceListResponse } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import { requestUrl } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { paginate, readPageQuery } from "../shared/pagination.js";
import { readContractBody } from "../shared/requestBody.js";

export function registerWorkspaceRoutes(router: Router, services: RouteServices): void {
    const create: RouteHandler = async ({ request, response }) => {
        const body = await readContractBody<WorkspaceCreateRequest>(
            request,
            services.validator,
            SCHEMA_REFS.workspaceCreateRequest,
        );
        const [workspace, created] = services.workspaces.create(body);
        // Best effort: Source/R0/PDF calls register again before they need the root.
        await services.serviceWorkspaces.tryEnsure(workspace.workspace_id);
        sendJson(response, created ? 201 : 200, workspace);
    };
    const list: RouteHandler = async ({ request, response }) => {
        const page = paginate(services.workspaces.list(), "workspaces", readPageQuery(requestUrl(request.url)));
        const body: WorkspaceListResponse = { schema_version: "1", items: page.items, page: page.page };
        sendJson(response, 200, body);
    };
    const get: RouteHandler = async ({ response, params }) => {
        sendJson(response, 200, services.workspaces.get(params.workspace_id ?? ""));
    };
    router.add("POST", "/api/v1/workspaces", create);
    router.add("GET", "/api/v1/workspaces", list);
    router.add("GET", "/api/v1/workspaces/:workspace_id", get);
}
