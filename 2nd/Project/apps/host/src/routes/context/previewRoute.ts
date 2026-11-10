/**
 * POST /api/v1/context/preview (3.6): plan (context.select with the session's real costs and history),
 * search (R0 candidates, no source text) and bundle (R0 source within caps). A plan's preview_digest
 * is what RunCreateRequest.preview_digest must echo.
 */
import { SCHEMA_REFS, type ContextPreviewRequest, type ContextPreviewResponse } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { readContractBody } from "../shared/requestBody.js";
import { RouteFailure } from "../shared/routeFailure.js";

export function registerPreviewRoute(router: Router, services: RouteServices): void {
    const preview: RouteHandler = async ({ request, response }) => {
        const body = await readContractBody<ContextPreviewRequest>(
            request,
            services.validator,
            SCHEMA_REFS.contextPreviewRequest,
        );
        const workspaceId = body.input.workspace_id;
        services.workspaces.get(workspaceId);
        await services.serviceWorkspaces.ensure(workspaceId);
        let result: ContextPreviewResponse;
        if (body.operation === "plan") {
            const session = services.sessions.get(body.input.session_id);
            if (session.workspace_id !== workspaceId) {
                throw new RouteFailure("FORBIDDEN", "session is outside this workspace");
            }
            const input = body.input;
            const selected = await services.assembler.select({
                workspace_id: input.workspace_id,
                session_id: input.session_id,
                prompt: input.prompt,
                context_refs: input.context_refs,
            });
            result = { operation: "plan", result: selected.plan };
        } else if (body.operation === "search") {
            result = { operation: "search", result: await services.contextClient.symbols.search(body.input) };
        } else {
            result = { operation: "bundle", result: await services.contextClient.symbols.readBundle(body.input) };
        }
        sendJson(response, 200, services.validator.parse(SCHEMA_REFS.contextPreviewResponse, result));
    };
    router.add("POST", "/api/v1/context/preview", preview);
}
