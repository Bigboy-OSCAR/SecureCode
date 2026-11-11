import type { RouteServices } from "../routeServices.js";
import type { Router } from "../router.js";
import { sendJson } from "../responses.js";
import { readJsonBody } from "../shared/requestBody.js";
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
        const body = await readJsonBody(request, 1024);
        if (
            !body ||
            typeof body !== "object" ||
            Array.isArray(body) ||
            Object.keys(body).length !== 1 ||
            !("model_id" in body) ||
            typeof body.model_id !== "string" ||
            body.model_id.length > 128
        ) {
            throw new RouteFailure("VALIDATION_FAILED", "모델을 선택하세요.");
        }
        if (!services.models) throw new RouteFailure("PROVIDER_ERROR", "이 실행에서는 모델 변경을 지원하지 않습니다.");
        sendJson(response, 200, await services.models.select(body.model_id));
    });
}
