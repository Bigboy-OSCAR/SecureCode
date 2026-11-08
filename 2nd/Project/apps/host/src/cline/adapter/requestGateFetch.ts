/**
 * ClineCoreOptions.fetch wrapper: the last point before a provider request
 * leaves the process (3.1 S-05). Every outbound body goes through the
 * ModelRequestGate port (4.8 owns the policy); a refused or unreadable body is
 * never sent, and the active turn records why it failed.
 */
import type { ModelRequestGate } from "./ports.js";
import { recordFailure, turnStorage } from "./turnContext.js";

export class GateBlockedError extends Error {
    readonly code: string;

    constructor(code: string, message: string) {
        super(message);
        this.name = "GateBlockedError";
        this.code = code;
    }
}

export interface GatedFetchOptions {
    gate: ModelRequestGate;
    baseFetch: typeof fetch;
    providerId: string;
    modelId: string;
    maxOutputTokens: number;
    /** Tool names the model may see; any other tool in the outbound body blocks the request (3.1 C-04). */
    allowedToolNames: ReadonlySet<string>;
}

/** Returns the first tool name that is not on the allow list, or null. */
export function unexpectedToolName(body: string, allowed: ReadonlySet<string>): string | null {
    let parsed: unknown;
    try {
        parsed = JSON.parse(body);
    } catch {
        return "<unparseable body>";
    }
    const tools = (parsed as { tools?: unknown }).tools;
    if (tools === undefined) return null;
    if (!Array.isArray(tools)) return "<tools is not a list>";
    for (const tool of tools as unknown[]) {
        const name = typeof tool === "object" && tool !== null ? (tool as { name?: unknown }).name : undefined;
        if (typeof name !== "string" || !allowed.has(name)) return typeof name === "string" ? name : "<unnamed tool>";
    }
    return null;
}

function bodyText(body: RequestInit["body"]): string | null {
    if (typeof body === "string") return body;
    if (body instanceof Uint8Array) return new TextDecoder("utf-8", { fatal: true }).decode(body);
    return null;
}

export function createGatedFetch(options: GatedFetchOptions): typeof fetch {
    return async (input, init) => {
        const turn = turnStorage.getStore();
        const body = bodyText(init?.body);
        if (body === null) {
            recordFailure(turn, { code: "BUDGET_EXCEEDED", message: "the model request could not be inspected" });
            throw new GateBlockedError("BUDGET_EXCEEDED", "outbound request body is not inspectable");
        }
        if (unexpectedToolName(body, options.allowedToolNames) !== null) {
            recordFailure(turn, {
                code: "PROTECTION_UNAVAILABLE",
                message: "the model request exposed a tool outside the allow list",
            });
            throw new GateBlockedError(
                "PROTECTION_UNAVAILABLE",
                "outbound request contains a tool outside the allow list",
            );
        }
        const signal = init?.signal ?? new AbortController().signal;
        let decision;
        try {
            decision = await options.gate.check(
                {
                    providerId: options.providerId,
                    modelId: options.modelId,
                    body,
                    maxOutputTokens: options.maxOutputTokens,
                },
                signal,
            );
        } catch {
            // A gate that cannot decide fails closed, like an unavailable tokenizer (0.7).
            recordFailure(turn, { code: "TOKENIZER_UNAVAILABLE", message: "the model request could not be counted" });
            throw new GateBlockedError("TOKENIZER_UNAVAILABLE", "model request gate failed");
        }
        if (!decision.allow) {
            recordFailure(turn, { code: decision.code, message: decision.message.slice(0, 500) });
            throw new GateBlockedError(decision.code, decision.message);
        }
        return options.baseFetch(input, init);
    };
}
