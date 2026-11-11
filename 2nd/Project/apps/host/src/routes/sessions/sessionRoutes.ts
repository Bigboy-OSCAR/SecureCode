/**
 * Session routes: POST /api/v1/sessions, GET /api/v1/sessions/:session_id and
 * GET /api/v1/workspaces/:workspace_id/sessions. Creating a session requires
 * every protection to be ready (PROTECTION_UNAVAILABLE otherwise).
 */
import { SCHEMA_REFS, type SessionCreateRequest, type SessionListResponse } from "@securecode/contracts";
import { requireProtections } from "../runs/runService.js";
import type { RouteServices } from "../routeServices.js";
import { requestUrl } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { paginate, readPageQuery } from "../shared/pagination.js";
import { readContractBody } from "../shared/requestBody.js";
import { RouteFailure } from "../shared/routeFailure.js";

export function registerSessionRoutes(router: Router, services: RouteServices): void {
    const create: RouteHandler = async ({ request, response }) => {
        const body = await readContractBody<SessionCreateRequest>(
            request,
            services.validator,
            SCHEMA_REFS.sessionCreateRequest,
        );
        services.workspaces.get(body.workspace_id);
        const scope = `sessions:${body.workspace_id}`;
        const lookup = services.idempotency.lookup(scope, body.idempotency_key, body);
        if (lookup.kind === "replay") {
            sendJson(response, 200, services.sessions.get(lookup.resultId));
            return;
        }
        requireProtections(services.protections());
        const session = services.sessions.create(body.workspace_id);
        services.idempotency.remember(scope, body.idempotency_key, lookup.bodyDigest, session.session_id);
        sendJson(response, 201, session);
    };
    const get: RouteHandler = async ({ response, params }) => {
        sendJson(response, 200, services.sessions.get(params.session_id ?? ""));
    };
    const listForWorkspace: RouteHandler = async ({ request, response, params }) => {
        const workspaceId = params.workspace_id ?? "";
        services.workspaces.get(workspaceId);
        const page = paginate(
            services.sessions.listForWorkspace(workspaceId),
            `sessions:${workspaceId}`,
            readPageQuery(requestUrl(request.url)),
        );
        const body: SessionListResponse = { schema_version: "1", items: page.items, page: page.page };
        sendJson(response, 200, body);
    };
    const remove: RouteHandler = async ({ response, params }) => {
        const sessionId = params.session_id ?? "";
        if (services.runs.hasActiveRuns(undefined, sessionId)) {
            throw new RouteFailure("RUN_ALREADY_ACTIVE", "대화의 실행을 완료하거나 취소한 뒤 삭제하세요.", {
                reason: "session_has_active_run",
            });
        }
        sendJson(response, 200, services.sessions.remove(sessionId));
    };
    const restore: RouteHandler = async ({ response, params }) => {
        const sessionId = params.session_id ?? "";
        services.workspaces.get(services.sessions.workspaceFor(sessionId));
        sendJson(response, 200, services.sessions.restore(sessionId));
    };
    router.add("POST", "/api/v1/sessions", create);
    router.add("GET", "/api/v1/sessions/:session_id", get);
    router.add("DELETE", "/api/v1/sessions/:session_id", remove);
    router.add("POST", "/api/v1/sessions/:session_id/restore", restore);
    router.add("GET", "/api/v1/workspaces/:workspace_id/sessions", listForWorkspace);
}
