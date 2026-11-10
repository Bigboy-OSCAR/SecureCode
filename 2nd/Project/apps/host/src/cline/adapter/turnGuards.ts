/**
 * Checks done before every SDK turn (start or send): all required hooks are registered, the
 * provider is configured and the Runtime store answers for this scope. A refusal means the SDK is
 * never called, so nothing can reach the model without the pointer protection in place (3.1 S-04).
 */
import type { ModelRequestGate, RuntimePointerService, ToolResultTransformer } from "./ports.js";
import type { TurnOutcome, TurnRequest } from "./runtimePort.js";

export interface TurnGuardOptions {
    transformer: ToolResultTransformer | null;
    gate: ModelRequestGate | null;
    runtimePointers: RuntimePointerService | null;
    apiKey: string | null;
    hookTimeoutMs: number;
}

export async function checkTurnReady(options: TurnGuardOptions, request: TurnRequest): Promise<TurnOutcome | null> {
    if (!options.transformer || !options.gate || !options.runtimePointers) {
        return {
            finish: "failed",
            text: "",
            reasonCode: "PROTECTION_UNAVAILABLE",
            message: "required hooks are not registered",
        };
    }
    if (!options.apiKey) {
        return {
            finish: "failed",
            text: "",
            reasonCode: "PROVIDER_ERROR",
            message: "the model provider is not configured",
        };
    }
    try {
        const scope = { workspaceId: request.workspaceId, sessionId: request.sessionId };
        await options.transformer.ready?.(scope, AbortSignal.timeout(options.hookTimeoutMs));
    } catch {
        return {
            finish: "failed",
            text: "",
            reasonCode: "PROTECTION_UNAVAILABLE",
            message: "the runtime pointer store is not reachable; the run was not started",
        };
    }
    return null;
}
