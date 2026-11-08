/**
 * POST /api/v1/runs/:run_id/approvals/:approval_id. The broker checks the
 * digest, expiry and pending state; one decision per approval_id.
 */
import { SCHEMA_REFS, type ApprovalDecisionRequest, type ApprovalDecisionResponse } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { readContractBody } from "../shared/requestBody.js";

export function registerApprovalRoutes(router: Router, services: RouteServices): void {
    const decide: RouteHandler = async ({ request, response, params }) => {
        const body = await readContractBody<ApprovalDecisionRequest>(
            request,
            services.validator,
            SCHEMA_REFS.approvalDecisionRequest,
        );
        const approval = services.runs.decide(params.run_id ?? "", params.approval_id ?? "", body);
        const result: ApprovalDecisionResponse = { schema_version: "1", approval };
        sendJson(response, 200, result);
    };
    router.add("POST", "/api/v1/runs/:run_id/approvals/:approval_id", decide);
}
