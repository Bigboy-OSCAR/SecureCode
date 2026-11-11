/**
 * 1.6 E2E regression: a cancel that lands while the request gate is still counting (before the SDK's
 * provider fetch exists) must stop the request. Before the fix the request was sent anyway with no live
 * abort signal and the run stayed "cancelling" while the provider held the connection.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { ModelRequestGate } from "../../src/cline/adapter/ports.js";
import { createGatedFetch } from "../../src/cline/adapter/requestGateFetch.js";
import { turnStorage, type ActiveTurn } from "../../src/cline/adapter/turnContext.js";

function turn(): ActiveTurn {
    return {
        workspaceId: "ws_00000001",
        sessionId: "ses_00000001",
        runId: "run_00000001",
        listener: () => undefined,
        failure: null,
        toolOutputs: new Map(),
        executorCaptures: new Map(),
        cancel: new AbortController(),
    };
}

function gated(gate: ModelRequestGate, baseFetch: typeof fetch): typeof fetch {
    return createGatedFetch({
        gate,
        baseFetch,
        providerId: "openai-compatible",
        modelId: "m",
        maxOutputTokens: 16,
        allowedToolNames: new Set(),
    });
}

const allow: ModelRequestGate = {
    check: () => Promise.resolve({ allow: true, countedTokens: 1, countMode: "exact" }),
};
const body = JSON.stringify({ model: "m", messages: [] });

test("an already cancelled turn sends nothing to the provider", async () => {
    const active = turn();
    active.cancel.abort(new DOMException("cancelled", "AbortError"));
    let sent = 0;
    const fetcher = gated(allow, () => {
        sent += 1;
        return Promise.resolve(new Response("{}"));
    });
    await assert.rejects(
        turnStorage.run(active, () => fetcher("http://127.0.0.1/v1/chat/completions", { method: "POST", body })),
        { name: "AbortError" },
    );
    assert.equal(sent, 0);
});

test("a cancel during counting is reported as an abort, not as a gate failure", async () => {
    const active = turn();
    const counting: ModelRequestGate = {
        check: (_request, signal) =>
            new Promise((_resolve, reject) => {
                signal.addEventListener("abort", () => reject(new Error("count aborted")), { once: true });
                active.cancel.abort(new DOMException("cancelled", "AbortError"));
            }),
    };
    const fetcher = gated(counting, () => Promise.resolve(new Response("{}")));
    await assert.rejects(
        turnStorage.run(active, () => fetcher("http://127.0.0.1/v1/chat/completions", { method: "POST", body })),
        { name: "AbortError" },
    );
    assert.equal(active.failure, null, "no TOKENIZER_UNAVAILABLE is recorded for a cancel");
});

test(
    "a request already sent is tied to the turn cancel even when the SDK gave no signal",
    { timeout: 5000 },
    async () => {
        const active = turn();
        let received: AbortSignal | null | undefined;
        const fetcher = gated(allow, (_input, init) => {
            received = init?.signal;
            return new Promise((_resolve, reject) => {
                init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), {
                    once: true,
                });
            });
        });
        const pending = turnStorage.run(active, () =>
            fetcher("http://127.0.0.1/v1/chat/completions", { method: "POST", body }),
        );
        await new Promise((resolve) => setImmediate(resolve));
        assert.ok(received instanceof AbortSignal && !received.aborted);
        active.cancel.abort(new DOMException("cancelled", "AbortError"));
        await assert.rejects(pending, { name: "AbortError" });
    },
);
