/**
 * Scenario: local tool → 64 KiB sentinel result → afterTool result replacement
 * → second provider request carries only the pointer. Also checks the SDK
 * canonical history, the persisted transcript, and the Core event stream.
 */
import { readFileSync } from "node:fs";
import type { CoreSessionEvent } from "@cline/sdk";
import { MemoryPointerFixture } from "../fixtures/memory-pointer-fixture.js";
import { createSentinelTool, SENTINEL_MARKER, SENTINEL_TOOL_NAME } from "../fixtures/probe-tools.js";
import { ScriptedProviderFetch } from "../fixtures/scripted-fetch.js";
import { createProbeCore } from "../probe/core-factory.js";
import { createPointerAfterToolHook, type PointerHookStats } from "../probe/pointer-hook.js";
import { buildProbeStartInput } from "../probe/session-config.js";
import { createFixtureWorkspace } from "../support/fixture-workspace.js";
import { isToolPairingPreserved, listToolNames, summarizeContentBlocks } from "../support/payload-inspect.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

export async function runPointerReplacementScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("pointer-replacement");
    const workspaceDir = createFixtureWorkspace("pointer-replacement");
    const store = new MemoryPointerFixture();
    const stats: PointerHookStats = { replacedCount: 0, passThroughCount: 0 };
    const scriptedFetch = new ScriptedProviderFetch([
        { toolUses: [{ toolUseId: "toolu_probe_1", toolName: SENTINEL_TOOL_NAME, input: { label: "big" } }] },
        { text: "Done. I received a pointer." },
    ]);
    const core = await createProbeCore({ fetch: scriptedFetch.fetch });
    const coreEvents: string[] = [];
    const unsubscribe = core.subscribe((event: CoreSessionEvent) => coreEvents.push(JSON.stringify(event)));

    try {
        const afterTool = createPointerAfterToolHook({ store, workspaceId: "ws_probe", thresholdBytes: 16 * 1024, timeoutMs: 2000 }, stats);
        const startInput = buildProbeStartInput({
            cwd: workspaceDir,
            prompt: "Generate the fixture log.",
            extraTools: [createSentinelTool()],
            hooks: { afterTool },
        });
        const started = await core.start(startInput);
        const requests = scriptedFetch.capturedRequests;
        const [firstRequest, secondRequest] = requests;
        const storedPointer = [...store.storedContents.keys()][0] ?? "<none>";

        recorder.check("two provider requests captured", requests.length === 2, `requests=${requests.length}`);
        recorder.check("first request has no sentinel", firstRequest !== undefined && !firstRequest.bodyText.includes(SENTINEL_MARKER), "request#1 body scanned");
        recorder.check("afterTool replaced the result", stats.replacedCount === 1 && store.storedContents.size === 1, `replaced=${stats.replacedCount}`);
        recorder.check("fixture stored full original", (store.storedContents.get(storedPointer)?.length ?? 0) === 64 * 1024, "stored bytes=65536");
        recorder.check("second request carries pointer", secondRequest?.bodyText.includes(storedPointer) ?? false, "pointer uri found in request#2");
        recorder.check("second request has no sentinel", secondRequest !== undefined && !secondRequest.bodyText.includes(SENTINEL_MARKER), `request#2 bytes=${secondRequest?.bodyBytes}`);
        recorder.check("tool_use/tool_result pairing preserved", secondRequest !== undefined && isToolPairingPreserved(secondRequest), "request#2 pairing");

        const canonical = JSON.stringify(await core.readMessages(started.sessionId));
        recorder.check("canonical history has pointer", canonical.includes(storedPointer), "readMessages contains pointer");
        recorder.check("canonical history has no sentinel", !canonical.includes(SENTINEL_MARKER), `history chars=${canonical.length}`);
        const persisted = readFileSync(started.messagesPath, "utf8");
        recorder.check("persisted transcript has no sentinel", !persisted.includes(SENTINEL_MARKER), "messages.json scanned");

        const eventsContainingSentinel = coreEvents.filter((serialized) => serialized.includes(SENTINEL_MARKER)).length;
        recorder.observe("core_events_total", coreEvents.length);
        recorder.observe("core_events_containing_sentinel", eventsContainingSentinel);
        recorder.observe("request2_block_order", secondRequest ? summarizeContentBlocks(secondRequest) : []);
        recorder.observe("request_bytes", requests.map((request) => request.bodyBytes));
        recorder.observe("request1_url_path", firstRequest ? new URL(firstRequest.url).pathname : "<none>");
        recorder.observe("request1_body_keys", firstRequest ? Object.keys(firstRequest.body).sort() : []);
        recorder.observe("request1_tool_names", firstRequest ? listToolNames(firstRequest) : []);
    } catch (error) {
        recorder.fail("scenario threw", error);
    } finally {
        unsubscribe();
        await core.dispose("probe finished");
    }
    return recorder.finish();
}
