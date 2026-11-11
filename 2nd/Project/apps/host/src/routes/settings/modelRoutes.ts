import { SCHEMA_REFS, type ModelSelectRequest } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import type { Router } from "../router.js";
import { sendJson } from "../responses.js";
import { readContractBody } from "../shared/requestBody.js";
import { RouteFailure } from "../shared/routeFailure.js";

export function registerModelRoutes(router: Router, services: RouteServices): void {
    router.add("GET", "/api/v1/models", async ({ response }) => {
        sendJson(
            response,
            200,
            services.models?.snapshot() ?? {
                schema_version: "1",
                active_model_id: services.settings().provider.model_id,
                status: "ready",
                error: null,
                items: [],
            },
        );
    });
    router.add("POST", "/api/v1/models/select", async ({ request, response }) => {
        const body = await readContractBody<ModelSelectRequest>(
            request,
            services.validator,
            SCHEMA_REFS.modelSelectRequest,
            1024,
        );
        if (!services.models) throw new RouteFailure("PROVIDER_ERROR", "이 실행에서는 모델 변경을 지원하지 않습니다.");
        sendJson(response, 200, await services.models.select(body.model_id));
    });
}
