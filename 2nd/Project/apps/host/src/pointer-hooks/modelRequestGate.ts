/**
 * 4.8 total model-request budget gate (ModelRequestGate port, wired into ClineCoreOptions.fetch by
 * 3.5). Every provider call is counted as the exact serialized body that would leave the process:
 * system, tool definitions, the whole history and the user turn, in the provider's own framing. The
 * context-service counts it (tokens.request); this gate adds the output reserve and safety margin and
 * allows or blocks. It never edits the body, so tool_use/tool_result pairs stay intact.
 *
 * Hard-cap mode accepts only an exact count (a tokenizer and framing verified for the model); an
 * estimate is then TOKENIZER_UNAVAILABLE. Outside hard-cap mode an estimate is used with a margin of at
 * least max(1024, 2% of the window). A count that cannot be made is never replaced by chars/4.
 */
import type { CountMode, RequestTokenCountRequest, TokenCountResult } from "@securecode/contracts";
import type { ModelRequestDecision, ModelRequestGate, OutboundModelRequest } from "../cline/adapter/ports.js";
import { turnStorage } from "../cline/adapter/turnContext.js";
import { ContextServiceError } from "../context-client/contextServiceError.js";

export const MIN_ESTIMATE_MARGIN = 1024;
export const ESTIMATE_MARGIN_RATIO = 0.02;

export interface RequestCounter {
    countRequest(request: RequestTokenCountRequest, signal?: AbortSignal): Promise<TokenCountResult>;
}

export interface ModelRequestGateOptions {
    counter: RequestCounter;
    contextLimitTokens: number;
    safetyMarginTokens: number;
    /** Hard-cap mode: block unless the request count is exact. */
    requireExactCount: boolean;
}

/** Margin actually applied for a count mode (CONTEXT_SELECTOR.md 3.1). */
export function appliedMargin(mode: CountMode, configured: number, limit: number): number {
    if (mode === "exact") return configured;
    return Math.max(configured, MIN_ESTIMATE_MARGIN, Math.ceil(limit * ESTIMATE_MARGIN_RATIO));
}

function parseBody(body: string): Record<string, unknown> | null {
    try {
        const parsed: unknown = JSON.parse(body);
        if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
            return parsed as Record<string, unknown>;
        }
    } catch {
        // falls through: an unparseable body cannot be counted
    }
    return null;
}

/** Code plus the machine reason and field name (never a value) from the service error. */
function describe(error: ContextServiceError): string {
    const details = error.details ?? {};
    const parts = [details.reason, details.field].filter((part) => typeof part === "string");
    return parts.length > 0 ? `${error.code}: ${parts.join(" ")}` : error.code;
}

function refuse(code: "BUDGET_EXCEEDED" | "TOKENIZER_UNAVAILABLE", message: string): ModelRequestDecision {
    return { allow: false, code, message };
}

/** Output tokens the provider may still produce: the larger of the configured and the body's max_tokens. */
function outputReserve(body: Record<string, unknown>, configured: number): number {
    const fromBody = body.max_tokens;
    return typeof fromBody === "number" && Number.isInteger(fromBody) && fromBody > configured ? fromBody : configured;
}

export function createModelRequestGate(options: ModelRequestGateOptions): ModelRequestGate {
    return {
        async check(request: OutboundModelRequest, signal: AbortSignal): Promise<ModelRequestDecision> {
            const body = parseBody(request.body);
            if (body === null) return refuse("TOKENIZER_UNAVAILABLE", "the model request is not a JSON object");
            let counted: TokenCountResult;
            try {
                counted = await options.counter.countRequest(
                    { schema_version: "1", provider_id: request.providerId, model_id: request.modelId, request: body },
                    signal,
                );
            } catch (error) {
                const reason = error instanceof ContextServiceError ? describe(error) : "count failed";
                return refuse("TOKENIZER_UNAVAILABLE", `the model request could not be counted (${reason})`);
            }
            if (options.requireExactCount && counted.count_mode !== "exact") {
                return refuse(
                    "TOKENIZER_UNAVAILABLE",
                    `hard-cap mode needs an exact count; ${request.providerId}/${request.modelId} only has ${counted.count_mode}`,
                );
            }
            const limit = options.contextLimitTokens;
            const reserve = outputReserve(body, request.maxOutputTokens);
            const margin = appliedMargin(counted.count_mode, options.safetyMarginTokens, limit);
            const total = counted.token_count + reserve + margin;
            if (total > limit) {
                return refuse(
                    "BUDGET_EXCEEDED",
                    `request ${counted.token_count} + output ${reserve} + margin ${margin} > window ${limit} tokens; ` +
                        "narrow the range or start a new session",
                );
            }
            const turn = turnStorage.getStore();
            if (turn) turn.remainingRequestTokens = limit - total;
            return { allow: true, countedTokens: counted.token_count, countMode: counted.count_mode };
        },
    };
}
