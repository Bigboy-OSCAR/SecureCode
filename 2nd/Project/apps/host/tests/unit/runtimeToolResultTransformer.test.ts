/** 4.4 transformer policies: inline / stored / executor-captured / bounded read, facts and fail-closed paths. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { it } from "node:test";
import type { ToolResultInput } from "../../src/cline/adapter/ports.js";
import { createRuntimeToolResultTransformer } from "../../src/pointer-hooks/runtimeToolResultTransformer.js";
import { FixtureRuntimeService } from "../support/fixtureHooks.js";

const SCOPE = { workspaceId: "ws_12345678", sessionId: "ses_12345678" };

function input(output: string, extra: Partial<ToolResultInput> = {}): ToolResultInput {
    return {
        ...SCOPE,
        runId: "run_12345678",
        toolCallId: "call_1",
        toolName: "list_files",
        output,
        outputBytes: Buffer.byteLength(output),
        preLimitedByExecutor: false,
        ...extra,
    };
}

const signal = (): AbortSignal => new AbortController().signal;

it("keeps small output inline without storing it", async () => {
    const service = new FixtureRuntimeService();
    const result = await createRuntimeToolResultTransformer(service).transform(input("small"), signal());
    assert.deepEqual(result, { kind: "inline", text: "small" });
    assert.equal(service.objects.size, 0);
});

it("stores large output once and exposes only a bounded descriptor", async () => {
    const service = new FixtureRuntimeService();
    const output = `SENTINEL-${"가".repeat(3000)}`;
    const result = await createRuntimeToolResultTransformer(service).transform(input(output), signal());
    assert.equal(result.kind, "pointer");
    assert.equal(service.objects.size, 1);
    assert.equal([...service.objects.values()][0], output);
    assert.ok(Buffer.byteLength(result.text) < 1500);
    assert.match(result.text, /capture: complete/);
    assert.ok(!result.text.includes("가".repeat(300)));
});

it("keeps command status, JSON facts and the tool error flag in the descriptor", async () => {
    const service = new FixtureRuntimeService();
    const transformer = createRuntimeToolResultTransformer(service);
    const json = JSON.stringify({ status: "failed", exit_code: 2, error: "boom", log: "x".repeat(5000) });
    const stored = await transformer.transform(input(json, { isError: true }), signal());
    assert.match(stored.text, /facts: \{"status":"failed","exit_code":2,"error":"boom"\}/);
    assert.match(stored.text, /tool_error: true/);
    const log = `${"line\n".repeat(2000)}[run_command: exit code 3]`;
    const command = await transformer.transform(input(log, { toolName: "run_command" }), signal());
    assert.match(command.text, /status: \[run_command: exit code 3\]/);
});

it("marks tool-limited output as truncated before storage", async () => {
    const service = new FixtureRuntimeService();
    const result = await createRuntimeToolResultTransformer(service).transform(
        input("y".repeat(5000), { preLimitedByExecutor: true }),
        signal(),
    );
    assert.match(result.text, /capture: truncated before storage by the tool; stored 5000 bytes/);
});

it("passes executor-streamed captures through without storing them again", async () => {
    const service = new FixtureRuntimeService();
    const transformer = createRuntimeToolResultTransformer(service);
    const pointer = `securecode://runtime/${SCOPE.workspaceId}/${SCOPE.sessionId}/11111111-2222-4333-8444-555555555555?v=1`;
    const capture = { pointer, byteSize: 10_000_000, producedBytes: 40_000_000, truncated: true };
    const result = await transformer.transform(
        input("[runtime pointer] descriptor", { executorStored: capture }),
        signal(),
    );
    assert.deepEqual(result, { kind: "pointer", pointer, byteSize: 10_000_000, text: "[runtime pointer] descriptor" });
    assert.equal(service.objects.size, 0);
    const foreign = { ...capture, pointer: pointer.replace("ses_12345678", "ses_87654321") };
    await assert.rejects(transformer.transform(input("x", { executorStored: foreign }), signal()));
    await assert.rejects(transformer.transform(input("x".repeat(9000), { executorStored: capture }), signal()));
});

it("never pointerizes bounded reads and rejects ones over their own cap", async () => {
    const service = new FixtureRuntimeService();
    const transformer = createRuntimeToolResultTransformer(service);
    const page = "z".repeat(20_000);
    for (const toolName of ["runtime_read", "runtime_search", "source_read", "pdf_read_pages"]) {
        assert.deepEqual(await transformer.transform(input(page, { toolName }), signal()), {
            kind: "inline",
            text: page,
        });
    }
    await assert.rejects(transformer.transform(input("z".repeat(40_000), { toolName: "runtime_read" }), signal()));
    assert.equal(service.objects.size, 0);
});

it("fails closed on store failure, mismatch, foreign pointer, abort and unreachable store", async () => {
    const big = "q".repeat(5000);
    const failing = new FixtureRuntimeService();
    failing.store = () => Promise.reject(new Error("store down"));
    await assert.rejects(createRuntimeToolResultTransformer(failing).transform(input(big), signal()), /store down/);
    const short = new FixtureRuntimeService();
    short.store = async () => ({
        pointer: `securecode://runtime/${SCOPE.workspaceId}/${SCOPE.sessionId}/x?v=1`,
        byteSize: 1,
    });
    await assert.rejects(createRuntimeToolResultTransformer(short).transform(input(big), signal()), /mismatch/);
    const foreign = new FixtureRuntimeService();
    foreign.store = async () => ({ pointer: "securecode://runtime/ws_other123/ses_12345678/x?v=1", byteSize: 5000 });
    await assert.rejects(createRuntimeToolResultTransformer(foreign).transform(input(big), signal()), /mismatch/);
    const hanging = new FixtureRuntimeService();
    hanging.store = () => new Promise(() => undefined);
    const controller = new AbortController();
    const pending = createRuntimeToolResultTransformer(hanging).transform(input(big), controller.signal);
    controller.abort(new Error("cancelled"));
    await assert.rejects(pending, /cancelled/);
    const unreachable = new FixtureRuntimeService();
    unreachable.mode = "unreachable";
    await assert.rejects(createRuntimeToolResultTransformer(unreachable).ready?.(SCOPE, signal()) ?? Promise.resolve());
});

it("applies the bounded-read policy to Source and PDF results shaped like the 4.2 contract fixtures", async () => {
    const fixtures = join(import.meta.dirname, "../../../../contracts/fixtures/pointers");
    const load = (name: string): unknown =>
        (JSON.parse(readFileSync(join(fixtures, name), "utf8")) as { data: unknown }).data;
    const service = new FixtureRuntimeService();
    const transformer = createRuntimeToolResultTransformer(service);
    const cases: [string, unknown][] = [
        ["source_read", load("read-result-truncated.valid.json")],
        ["source_search", load("search-result.valid.json")],
        ["pdf_read_pages", load("pdf-page-read.valid.json")],
    ];
    for (const [toolName, data] of cases) {
        const output = JSON.stringify(data);
        assert.deepEqual(await transformer.transform(input(output, { toolName }), signal()), {
            kind: "inline",
            text: output,
        });
    }
    const oversized = JSON.stringify({ ...(load("pdf-page-read.valid.json") as object), content: "가".repeat(12000) });
    await assert.rejects(transformer.transform(input(oversized, { toolName: "pdf_read_pages" }), signal()), /own cap/);
    assert.equal(service.objects.size, 0);
});
