/**
 * Scenario: runtime_read tool reads a stored pointer in bounded slices and
 * returns the original content across two calls.
 */
import type { CoreSessionEvent } from "@cline/sdk";
import { MemoryPointerFixture } from "../fixtures/memory-pointer-fixture.js";
import { ScriptedProviderFetch } from "../fixtures/scripted-fetch.js";
import { createProbeCore } from "../probe/core-factory.js";
import { buildProbeStartInput } from "../probe/session-config.js";
import { createFixtureWorkspace } from "../support/fixture-workspace.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

function createReadTool(store: MemoryPointerFixture) {
    return {
        name: "runtime_read",
        description: "Read a bounded slice of a Runtime Pointer.",
        inputSchema: {
            type: "object",
            properties: {
                pointer: { type: "string" },
                offset: { type: "integer", minimum: 0 },
                max_bytes: { type: "integer", minimum: 1, maximum: 16384 },
            },
            required: ["pointer"],
            additionalProperties: false,
        },
        execute: async (input: unknown) => {
            const record = input as { pointer?: string; offset?: number; max_bytes?: number };
            const pointer = typeof record.pointer === "string" ? record.pointer : "";
            const offset = typeof record.offset === "number" ? record.offset : 0;
            const maxBytes = typeof record.max_bytes === "number" ? record.max_bytes : 16384;
            const content = store.storedContents.get(pointer) ?? "";
            const slice = content.slice(offset, offset + maxBytes);
            return JSON.stringify({
                content: slice,
                truncated: offset + maxBytes < content.length,
                next_cursor: offset + slice.length,
                byte_size: content.length,
            });
        },
    } as const;
}

export async function runRuntimeReadScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("runtime-read");
    const workspaceDir = createFixtureWorkspace("runtime-read");
    const store = new MemoryPointerFixture();
    const content = "first\nneedle here\nthird";
    const stored = await store.put(content, "ws_probe", "ses_probe");
    const pointer = stored.pointer;
    const scriptedFetch = new ScriptedProviderFetch([
        {
            toolUses: [
                {
                    toolUseId: "toolu_read_1",
                    toolName: "runtime_read",
                    input: { pointer, offset: 0, max_bytes: 10 },
                },
            ],
        },
        {
            toolUses: [
                {
                    toolUseId: "toolu_read_2",
                    toolName: "runtime_read",
                    input: { pointer, offset: 10 },
                },
            ],
        },
        { text: "Done." },
    ]);
    const core = await createProbeCore({ fetch: scriptedFetch.fetch });
    const events: string[] = [];
    const unsubscribe = core.subscribe((event: CoreSessionEvent) => events.push(JSON.stringify(event)));

    try {
        const started = await core.start(
            buildProbeStartInput({
                cwd: workspaceDir,
                prompt: "Read the stored pointer.",
                extraTools: [createReadTool(store)],
                hooks: {},
            }),
        );
        const requests = scriptedFetch.capturedRequests;
        recorder.check("three provider requests captured", requests.length === 3, `requests=${requests.length}`);
        recorder.check(
            "first read returned prefix",
            requests[1]?.bodyText.includes("runtime_read") ?? false,
            "request#2 scanned",
        );
        recorder.check(
            "second read returned remainder",
            requests[2]?.bodyText.includes("runtime_read") ?? false,
            "request#3 scanned",
        );
        recorder.check(
            "pointer never exposed raw",
            !requests[1]?.bodyText.includes(content) && !requests[2]?.bodyText.includes(content),
            "raw content absent",
        );
        recorder.check("session started", started.sessionId.length > 0, `session=${started.sessionId}`);
        recorder.observe("request_count", requests.length);
        recorder.observe("event_count", events.length);
    } catch (error) {
        recorder.fail("scenario threw", error);
    } finally {
        unsubscribe();
        await core.dispose("probe finished");
    }
    return recorder.finish();
}
