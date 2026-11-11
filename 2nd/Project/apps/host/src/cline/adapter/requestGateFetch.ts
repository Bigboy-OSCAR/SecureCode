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
    /** Sees each allowed body as it leaves (the Selector's history cost source). */
    onOutbound?: (sessionId: string, body: string) => void;
}

/** Tool name in Anthropic ({name}) or OpenAI-compatible ({type:"function", function:{name}}) framing. */
function toolName(tool: unknown): unknown {
    if (typeof tool !== "object" || tool === null) return undefined;
    const entry = tool as { name?: unknown; type?: unknown; function?: { name?: unknown } };
    if (entry.type === "function" && typeof entry.function === "object" && entry.function !== null) {
        return entry.function.name;
    }
    return entry.name;
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
        const name = toolName(tool);
        if (typeof name !== "string" || !allowed.has(name)) return typeof name === "string" ? name : "<unnamed tool>";
    }
    return null;
}

function bodyText(body: RequestInit["body"]): string | null {
    if (typeof body === "string") return body;
    if (body instanceof Uint8Array) return new TextDecoder("utf-8", { fatal: true }).decode(body);
    return null;
}

function linkedSignal(...signals: (AbortSignal | null | undefined)[]): AbortSignal {
    const present = signals.filter((signal): signal is AbortSignal => signal instanceof AbortSignal);
    return present.length === 0 ? new AbortController().signal : AbortSignal.any(present);
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
        // The SDK signal and the turn cancel both stop the request; an already cancelled turn sends nothing.
        const signal = linkedSignal(init?.signal, turn?.cancel.signal);
        signal.throwIfAborted();
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
            // A cancel during counting is a cancel, not a gate failure.
            signal.throwIfAborted();
            // A gate that cannot decide fails closed, like an unavailable tokenizer (0.7).
            recordFailure(turn, { code: "TOKENIZER_UNAVAILABLE", message: "the model request could not be counted" });
            throw new GateBlockedError("TOKENIZER_UNAVAILABLE", "model request gate failed");
        }
        if (!decision.allow) {
            recordFailure(turn, { code: decision.code, message: decision.message.slice(0, 500) });
            throw new GateBlockedError(decision.code, decision.message);
        }
        signal.throwIfAborted();
        if (turn) options.onOutbound?.(turn.sessionId, body);
        return options.baseFetch(input, { ...init, signal });
    };
}
