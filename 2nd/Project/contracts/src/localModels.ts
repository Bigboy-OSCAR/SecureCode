/** Local-only model controls. Paths, endpoints and credentials stay on the host. */
export interface LocalModel {
    model_id: string;
    display_name: string;
    runtime: "llama-cpp" | "lm-studio";
    context_limit_tokens: number;
    available: boolean;
    reason?: string;
}

export interface ModelListResponse {
    schema_version: "1";
    active_model_id: string | null;
    status: "ready" | "loading" | "error";
    error: string | null;
    items: LocalModel[];
}

export function parseModelListResponse(value: unknown): ModelListResponse {
    if (typeof value !== "object" || value === null) throw new Error("invalid model response");
    const data = value as Record<string, unknown>;
    if (
        data.schema_version !== "1" ||
        !["ready", "loading", "error"].includes(String(data.status)) ||
        !(data.active_model_id === null || typeof data.active_model_id === "string") ||
        !(data.error === null || typeof data.error === "string") ||
        !Array.isArray(data.items) ||
        data.items.length > 100 ||
        !data.items.every((item: unknown) => {
            if (typeof item !== "object" || item === null) return false;
            const model = item as Record<string, unknown>;
            return (
                typeof model.model_id === "string" &&
                typeof model.display_name === "string" &&
                ["llama-cpp", "lm-studio"].includes(String(model.runtime)) &&
                typeof model.available === "boolean" &&
                Number.isSafeInteger(model.context_limit_tokens) &&
                Number(model.context_limit_tokens) >= 1024 &&
                (model.reason === undefined || typeof model.reason === "string")
            );
        })
    )
        throw new Error("invalid model response");
    return value as ModelListResponse;
}
