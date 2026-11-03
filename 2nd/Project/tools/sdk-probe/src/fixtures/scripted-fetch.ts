/**
 * Scripted provider transport injected through `ClineCoreOptions.fetch`.
 * It sits after the SDK's provider message conversion and tool framing, so the
 * captured body is the exact outbound HTTP payload. It never contacts a network.
 */
import { buildTurnSseBody, type ScriptedTurn } from "./anthropic-sse.js";

export interface CapturedRequest {
    url: string;
    method: string;
    bodyText: string;
    bodyBytes: number;
    body: Record<string, unknown>;
}

export interface OutboundGateDecision {
    allowed: boolean;
    reason?: string;
}

export type OutboundGate = (request: CapturedRequest) => OutboundGateDecision;

export class OutboundBlockedError extends Error {
    readonly code = "BUDGET_EXCEEDED";
}

const FIXTURE_MODEL_ID = "claude-sonnet-5-5";

function readBodyText(init: RequestInit | undefined): string {
    const body = init?.body;
    if (typeof body === "string") {
        return body;
    }
    if (body instanceof Uint8Array) {
        return new TextDecoder().decode(body);
    }
    throw new Error("scripted fetch only supports string or byte request bodies");
}

function waitForAbort(signal: AbortSignal | null | undefined): Promise<never> {
    return new Promise((_resolve, reject) => {
        if (!signal) {
            reject(new Error("holdUntilAborted turn received a request without an AbortSignal"));
            return;
        }
        const rejectWithReason = (): void => reject(signal.reason ?? new DOMException("aborted", "AbortError"));
        if (signal.aborted) {
            rejectWithReason();
            return;
        }
        signal.addEventListener("abort", rejectWithReason, { once: true });
    });
}

export class ScriptedProviderFetch {
    readonly capturedRequests: CapturedRequest[] = [];
    readonly blockedRequests: CapturedRequest[] = [];
    private readonly pendingTurns: ScriptedTurn[];
    private readonly outboundGate: OutboundGate | undefined;

    constructor(turns: ScriptedTurn[], outboundGate?: OutboundGate) {
        this.pendingTurns = [...turns];
        this.outboundGate = outboundGate;
    }

    readonly fetch: typeof fetch = async (input, init) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const bodyText = readBodyText(init);
        const captured: CapturedRequest = {
            url,
            method: init?.method ?? "GET",
            bodyText,
            bodyBytes: Buffer.byteLength(bodyText, "utf8"),
            body: JSON.parse(bodyText) as Record<string, unknown>,
        };

        // The gate runs on the final serialized payload; a blocked request never leaves the process.
        const decision = this.outboundGate?.(captured) ?? { allowed: true };
        if (!decision.allowed) {
            this.blockedRequests.push(captured);
            throw new OutboundBlockedError(decision.reason ?? "outbound payload blocked");
        }
        this.capturedRequests.push(captured);

        const turn = this.pendingTurns.shift();
        if (!turn) {
            const errorBody = { type: "error", error: { type: "invalid_request_error", message: "scripted turns exhausted" } };
            return new Response(JSON.stringify(errorBody), { status: 400, headers: { "content-type": "application/json" } });
        }
        if (turn.holdUntilAborted) {
            await waitForAbort(init?.signal);
        }

        const messageId = `msg_probe_${this.capturedRequests.length}`;
        return new Response(buildTurnSseBody(turn, messageId, FIXTURE_MODEL_ID), {
            status: 200,
            headers: { "content-type": "text/event-stream", "request-id": messageId },
        });
    };
}
