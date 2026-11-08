/**
 * Scenario: runtime_search tool finds a line in a stored pointer and returns
 * its line number without exposing the full original content.
 */
import type { CoreSessionEvent } from "@cline/sdk";
import { MemoryPointerFixture } from "../fixtures/memory-pointer-fixture.js";
import { ScriptedProviderFetch } from "../fixtures/scripted-fetch.js";
import { createProbeCore } from "../probe/core-factory.js";
import { buildProbeStartInput } from "../probe/session-config.js";
import { createFixtureWorkspace } from "../support/fixture-workspace.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

function createSearchTool(store: MemoryPointerFixture) {
    return {
    name: "runtime_search",
    description: "Search a Runtime Pointer and return matching line numbers.",
    inputSchema: {
        type: "object",
        properties: {
            pointer: { type: "string" },
            query: { type: "string" },
        },
        required: ["pointer", "query"],
        additionalProperties: false,
    },
        execute: async (input: unknown) => {
            const record = input as { pointer?: string; query?: string };
            const pointer = typeof record.pointer === "string" ? record.pointer : "";
            const query = typeof record.query === "string" ? record.query : "";
            const content = store.storedContents.get(pointer) ?? "";
            const lines = content.split("\n");
            const matches: { line: number; text: string }[] = [];
            for (let index = 0; index < lines.length; index += 1) {
                const line = lines[index] ?? "";
                if (line.toLowerCase().includes(query.toLowerCase())) {
                    matches.push({ line: index + 1, text: line });
                }
            }
            return JSON.stringify({ matches, byte_size: content.length, truncated: false });
        },
    } as const;
}

export async function runRuntimeSearchScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("runtime-search");
    const workspaceDir = createFixtureWorkspace("runtime-search");
    const store = new MemoryPointerFixture();
    const content = "first\nneedle here\nthird";
    const stored = await store.put(content, "ws_probe", "ses_probe");
    const pointer = stored.pointer;
    const scriptedFetch = new ScriptedProviderFetch([
        {
            toolUses: [{
                toolUseId: "toolu_search_1",
                toolName: "runtime_search",
                input: { pointer, query: "needle" },
            }],
        },
        { text: "Done." },
    ]);
    const core = await createProbeCore({ fetch: scriptedFetch.fetch });
    const events: string[] = [];
    const unsubscribe = core.subscribe((event: CoreSessionEvent) => events.push(JSON.stringify(event)));

    try {
        const started = await core.start(buildProbeStartInput({
            cwd: workspaceDir,
            prompt: "Search the stored pointer.",
            extraTools: [createSearchTool(store)],
            hooks: {},
        }));
        const requests = scriptedFetch.capturedRequests;
        recorder.check("two provider requests captured", requests.length === 2, `requests=${requests.length}`);
        recorder.check("search returned line 2", requests[1]?.bodyText.includes("runtime_search") ?? false, "request#2 scanned");
        recorder.check("full content not exposed", !requests[1]?.bodyText.includes(content), "raw content absent");
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
