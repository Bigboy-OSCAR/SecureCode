/**
 * Run routes: POST/GET /api/v1/sessions/:session_id/runs, GET /api/v1/runs/:run_id
 * (snapshot, optional approval_cursor|citation_cursor) and POST .../cancel.
 */
import { SCHEMA_REFS, type RunCreateRequest } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import { requestUrl } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { readPageQuery } from "../shared/pagination.js";
import { readContractBody, RUN_BODY_LIMIT_BYTES } from "../shared/requestBody.js";
import { RouteFailure } from "../shared/routeFailure.js";
import type { SnapshotQuery } from "./runRecord.js";

function readSnapshotQuery(url: URL): SnapshotQuery {
    const approvalCursor = url.searchParams.get("approval_cursor");
    const citationCursor = url.searchParams.get("citation_cursor");
    if (approvalCursor !== null && citationCursor !== null) {
        throw new RouteFailure("VALIDATION_FAILED", "use either approval_cursor or citation_cursor", {
            reason: "cursor",
        });
    }
    return {
        ...(approvalCursor ? { approvalCursor } : {}),
        ...(citationCursor ? { citationCursor } : {}),
    };
}

export function registerRunRoutes(router: Router, services: RouteServices): void {
    const create: RouteHandler = async ({ request, response, params }) => {
        const body = await readContractBody<RunCreateRequest>(
            request,
            services.validator,
            SCHEMA_REFS.runCreateRequest,
            RUN_BODY_LIMIT_BYTES,
        );
        const result = services.runs.create(params.session_id ?? "", body);
        sendJson(response, result.created ? 201 : 200, result.snapshot);
    };
    const list: RouteHandler = async ({ request, response, params }) => {
        sendJson(response, 200, services.runs.list(params.session_id ?? "", readPageQuery(requestUrl(request.url))));
    };
    const get: RouteHandler = async ({ request, response, params }) => {
        sendJson(
            response,
            200,
            services.runs.snapshot(params.run_id ?? "", readSnapshotQuery(requestUrl(request.url))),
        );
    };
    const cancel: RouteHandler = async ({ response, params }) => {
        sendJson(response, 200, await services.runs.cancel(params.run_id ?? ""));
    };
    router.add("POST", "/api/v1/sessions/:session_id/runs", create);
    router.add("GET", "/api/v1/sessions/:session_id/runs", list);
    router.add("GET", "/api/v1/runs/:run_id", get);
    router.add("POST", "/api/v1/runs/:run_id/cancel", cancel);
}
