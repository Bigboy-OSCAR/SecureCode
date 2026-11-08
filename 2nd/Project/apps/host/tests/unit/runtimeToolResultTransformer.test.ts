/** Verify the Runtime Pointer replacement policy without a live SDK. */
import assert from "node:assert/strict";
import { it } from "node:test";
import type { ToolResultInput } from "../../src/cline/adapter/ports.js";
import {
    createRuntimeToolResultTransformer,
    type RuntimePointerStore,
} from "../../src/pointer-hooks/runtimeToolResultTransformer.js";

const ID = "11111111-aaaa-4444-bbbb-222222222222";
const PREFIX = "securecode://runtime/ws_12345678/ses_12345678/";

function input(output: string, overrides: Partial<ToolResultInput> = {}): ToolResultInput {
    return {
        workspaceId: "ws_12345678",
        sessionId: "ses_12345678",
        runId: "run_1",
        toolCallId: "call_1",
        toolName: "run_command",
        output,
        outputBytes: Buffer.byteLength(output),
        preLimitedByExecutor: false,
        ...overrides,
    };
}

function fakeStore(overrides: Partial<{ uri: string; size: number; fail: boolean }> = {}) {
    const calls: string[] = [];
    const store: RuntimePointerStore = {
        async store(content) {
            calls.push(content);
            if (overrides.fail) throw new Error("store down");
            return {
                pointerUri: overrides.uri ?? `${PREFIX}${ID}?v=1`,
                byteSize: overrides.size ?? Buffer.byteLength(content),
            };
        },
    };
    return { store, calls };
}

it("keeps small output inline without storing it", async () => {
    const { store, calls } = fakeStore();
    const result = await createRuntimeToolResultTransformer(store).transform(
        input("small"),
        new AbortController().signal,
    );
    assert.deepEqual(result, { kind: "inline", text: "small" });
    assert.equal(calls.length, 0);
});

it("stores large output once and exposes only a bounded descriptor", async () => {
    const { store, calls } = fakeStore();
    const secret = "SENTINEL-".repeat(2000);
    const result = await createRuntimeToolResultTransformer(store).transform(
        input(secret),
        new AbortController().signal,
    );
    assert.equal(result.kind, "pointer");
    assert.equal(calls.length, 1);
    assert.equal(calls[0], secret);
    assert.ok(Buffer.byteLength(result.text) < 1500);
    assert.ok(!result.text.includes(secret));
    assert.ok(result.text.includes(`${PREFIX}${ID}?v=1`));
});

it("preserves the command status and JSON facts when replacing output", async () => {
    const { store } = fakeStore();
    const transformer = createRuntimeToolResultTransformer(store);
    const signal = new AbortController().signal;
    const command = await transformer.transform(input(`${"x".repeat(5000)}\n[run_command: exit code 2]`), signal);
    assert.ok(command.text.includes("[run_command: exit code 2]"));
    const json = await transformer.transform(
        input(JSON.stringify({ status: "failed", exit_code: 1, log: "y".repeat(6000) })),
        signal,
    );
    assert.ok(json.text.includes('"exit_code":1'));
    assert.ok(json.text.includes('"status":"failed"'));
});

it("marks executor-limited output as partially captured", async () => {
    const { store } = fakeStore();
    const result = await createRuntimeToolResultTransformer(store).transform(
        input("z".repeat(5000), { preLimitedByExecutor: true }),
        new AbortController().signal,
    );
    assert.ok(result.text.includes("limited by the executor"));
});

it("fails closed on store failure, mismatch, foreign pointer and abort", async () => {
    const big = "q".repeat(5000);
    const signal = new AbortController().signal;
    await assert.rejects(
        createRuntimeToolResultTransformer(fakeStore({ fail: true }).store).transform(input(big), signal),
    );
    await assert.rejects(
        createRuntimeToolResultTransformer(fakeStore({ size: 1 }).store).transform(input(big), signal),
    );
    await assert.rejects(
        createRuntimeToolResultTransformer(
            fakeStore({ uri: `securecode://runtime/ws_other/ses_x/${ID}?v=1` }).store,
        ).transform(input(big), signal),
    );
    const aborted = new AbortController();
    aborted.abort(new Error("cancelled"));
    const { store, calls } = fakeStore();
    await assert.rejects(createRuntimeToolResultTransformer(store).transform(input(big), aborted.signal), /cancelled/);
    assert.equal(calls.length, 0);
});

it("never pointerizes bounded reads and rejects ones over their own cap", async () => {
    const { store, calls } = fakeStore();
    const transformer = createRuntimeToolResultTransformer(store);
    const signal = new AbortController().signal;
    const ok = await transformer.transform(input("r".repeat(10_000), { toolName: "runtime_read" }), signal);
    assert.equal(ok.kind, "inline");
    await assert.rejects(transformer.transform(input("r".repeat(40_000), { toolName: "runtime.read" }), signal));
    assert.equal(calls.length, 0);
});
