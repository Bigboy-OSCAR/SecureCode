/**
 * POST /api/v1/pdf/parse and GET /api/v1/pdf/jobs/:job_id (3.6) over the 4.9 PDF service. Responses carry
 * job metadata only (no extracted text). Job IDs are workspace-scoped in the service, so the host keeps
 * job → workspace from parse responses; an unknown job is NOT_FOUND (parse again after a host restart).
 */
import { SCHEMA_REFS, type PdfParseRequest } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { readContractBody } from "../shared/requestBody.js";
import { RouteFailure } from "../shared/routeFailure.js";

export function registerPdfRoutes(router: Router, services: RouteServices): void {
    const parse: RouteHandler = async ({ request, response }) => {
        const body = await readContractBody<PdfParseRequest>(request, services.validator, SCHEMA_REFS.pdfParseRequest);
        services.workspaces.get(body.workspace_id);
        await services.serviceWorkspaces.ensure(body.workspace_id);
        const status = await services.contextClient.pdf.parse(
            body.workspace_id,
            body.pointer,
            body.idempotency_key,
            AbortSignal.timeout(15000),
        );
        services.pdfJobs.set(status.job_id, body.workspace_id);
        sendJson(response, 200, status);
    };
    const job: RouteHandler = async ({ response, params }) => {
        const jobId = params.job_id ?? "";
        const workspaceId = services.pdfJobs.get(jobId);
        if (!workspaceId) throw new RouteFailure("NOT_FOUND", "PDF job not found");
        const status = await services.contextClient.pdf.status(workspaceId, jobId, AbortSignal.timeout(15000));
        sendJson(response, 200, status);
    };
    router.add("POST", "/api/v1/pdf/parse", parse);
    router.add("GET", "/api/v1/pdf/jobs/:job_id", job);
}
