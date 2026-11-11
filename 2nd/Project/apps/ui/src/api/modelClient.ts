/** Authenticated host-only model selection; no provider credentials enter the browser. */
import { parseModelListResponse, type ModelListResponse } from "../../../../contracts/src/localModels.js";
import { ApiClientError } from "./apiErrors.js";

export class ModelClient {
    async list(): Promise<ModelListResponse> {
        return this.request();
    }
    async select(modelId: string): Promise<ModelListResponse> {
        return this.request(modelId);
    }
    private async request(modelId?: string): Promise<ModelListResponse> {
        const response = await fetch(`/api/v1/models${modelId ? "/select" : ""}`, {
            method: modelId ? "POST" : "GET",
            credentials: "same-origin",
            headers: { "content-type": "application/json" },
            ...(modelId ? { body: JSON.stringify({ model_id: modelId }) } : {}),
            signal: AbortSignal.timeout(modelId ? 300000 : 15000),
        });
        if (!response.ok)
            throw new ApiClientError(
                "request",
                response.status === 409
                    ? "실행 중인 대화가 끝난 뒤 모델을 변경하세요."
                    : "모델을 불러오지 못했습니다. 로컬 모델 설정을 확인하세요.",
                response.status,
            );
        return parseModelListResponse(await response.json());
    }
}
