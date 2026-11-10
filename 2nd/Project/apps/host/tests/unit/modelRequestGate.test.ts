/** 4.8 request gate: exact/estimate modes, reserve and margin arithmetic, boundaries, failures and read caps. */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CountMode, RequestTokenCountRequest, TokenCountResult } from "@securecode/contracts";
import { turnStorage, type ActiveTurn } from "../../src/cline/adapter/turnContext.js";
import { readTokenCap } from "../../src/cline/tools/runtimeTools.js";
import { ContextServiceError } from "../../src/context-client/contextServiceError.js";
import {
    appliedMargin,
    createModelRequestGate,
    type RequestCounter,
} from "../../src/pointer-hooks/modelRequestGate.js";

const BODY = {
    model: "claude-sonnet-5-5",
    max_tokens: 1024,
    system: "시스템",
    messages: [
        { role: "user", content: "안녕 🌏" },
        { role: "assistant", content: [{ type: "tool_use", id: "t1", name: "read_file", input: {} }] },
        { role: "user", content: [{ type: "tool_result", tool_use_id: "t1", content: "결과" }] },
    ],
    tools: [{ name: "read_file", input_schema: { type: "object" } }],
};

class FakeCounter implements RequestCounter {
    readonly seen: RequestTokenCountRequest[] = [];
    constructor(
        private readonly tokens: number,
        private readonly mode: CountMode = "provider_estimate",
        private readonly failure: Error | null = null,
    ) {}

    countRequest(request: RequestTokenCountRequest): Promise<TokenCountResult> {
        this.seen.push(request);
        if (this.failure) return Promise.reject(this.failure);
        return Promise.resolve({
            schema_version: "1",
            token_count: this.tokens,
            count_mode: this.mode,
            provider_id: "anthropic",
            model_id: "claude-sonnet-5-5",
            method: "anthropic_count_tokens",
            framing: "provider_request",
            text_bytes: 10,
            cached: false,
        });
    }
}

function gateWith(counter: RequestCounter, requireExactCount = false, limit = 100_000) {
    return createModelRequestGate({ counter, contextLimitTokens: limit, safetyMarginTokens: 500, requireExactCount });
}

const outbound = (body: unknown = BODY, maxOutputTokens = 2048) => ({
    providerId: "anthropic",
    modelId: "claude-sonnet-5-5",
    body: JSON.stringify(body),
    maxOutputTokens,
});
const signal = new AbortController().signal;

test("counts the exact outbound body and allows it inside the window", async () => {
    const counter = new FakeCounter(1000);
    const decision = await gateWith(counter).check(outbound(), signal);
    assert.deepEqual(decision, { allow: true, countedTokens: 1000, countMode: "provider_estimate" });
    assert.deepEqual(counter.seen[0]?.request, BODY);
});

test("estimate margin is at least max(1024, 2% of the window); exact keeps the configured margin", () => {
    assert.equal(appliedMargin("provider_estimate", 500, 100_000), 2000);
    assert.equal(appliedMargin("provider_estimate", 500, 10_000), 1024);
    assert.equal(appliedMargin("provider_estimate", 5000, 10_000), 5000);
    assert.equal(appliedMargin("exact", 500, 100_000), 500);
});

test("the window boundary is inclusive and one token more is BUDGET_EXCEEDED", async () => {
    // 100000 = counted + reserve(max(2048, body 1024)) + margin(2000)
    const fits = await gateWith(new FakeCounter(100_000 - 2048 - 2000)).check(outbound(), signal);
    assert.equal(fits.allow, true);
    const over = await gateWith(new FakeCounter(100_000 - 2048 - 2000 + 1)).check(outbound(), signal);
    assert.equal(over.allow, false);
    assert.equal(!over.allow && over.code, "BUDGET_EXCEEDED");
});

test("a larger max_tokens in the body is reserved instead of the configured output", async () => {
    const body = { ...BODY, max_tokens: 8000 };
    const tight = await gateWith(new FakeCounter(100_000 - 8000 - 2000 + 1)).check(outbound(body), signal);
    assert.equal(tight.allow, false);
});

test("hard-cap mode blocks estimates and accepts exact counts", async () => {
    const estimate = await gateWith(new FakeCounter(10), true).check(outbound(), signal);
    assert.equal(!estimate.allow && estimate.code, "TOKENIZER_UNAVAILABLE");
    const exact = await gateWith(new FakeCounter(100_000 - 2048 - 500, "exact"), true).check(outbound(), signal);
    assert.deepEqual(exact, { allow: true, countedTokens: 100_000 - 2048 - 500, countMode: "exact" });
});

test("an uncountable request is TOKENIZER_UNAVAILABLE, never a chars/4 guess", async () => {
    const failure = new ContextServiceError("TOKENIZER_UNAVAILABLE", "no counter", false);
    const failed = await gateWith(new FakeCounter(0, "provider_estimate", failure)).check(outbound(), signal);
    assert.equal(!failed.allow && failed.code, "TOKENIZER_UNAVAILABLE");
    const counter = new FakeCounter(1);
    const garbled = await gateWith(counter).check({ ...outbound(), body: "not json" }, signal);
    assert.equal(!garbled.allow && garbled.code, "TOKENIZER_UNAVAILABLE");
    assert.equal(counter.seen.length, 0);
});

test("an allowed request leaves the remaining window for bounded tool reads", async () => {
    const turn = { remainingRequestTokens: undefined } as unknown as ActiveTurn;
    await turnStorage.run(turn, async () => {
        assert.equal(readTokenCap(), null);
        await gateWith(new FakeCounter(100_000 - 2048 - 2000 - 1256)).check(outbound(), signal);
        assert.equal(turn.remainingRequestTokens, 1256);
        assert.equal(readTokenCap(), 1000);
        turn.remainingRequestTokens = 200;
        assert.throws(() => readTokenCap(), /BUDGET_EXCEEDED/);
    });
});
