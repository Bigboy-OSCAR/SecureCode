/**
 * Scenario: the pointer afterTool hook fails (storage error / storage timeout).
 * With `hookErrorMode: "throw"` the run must fail and the sentinel must never
 * reach a provider request, history, or Core events. Also records how the SDK
 * behaves with "ignore" and with a hook that hangs without its own timeout.
 */
import type { AgentHooks } from "@cline/sdk";
import { MemoryPointerFixture, type PointerFailureMode } from "../fixtures/memory-pointer-fixture.js";
import { createSentinelTool, SENTINEL_MARKER, SENTINEL_TOOL_NAME } from "../fixtures/probe-tools.js";
import { createPointerAfterToolHook } from "../probe/pointer-hook.js";
import { errorMessage, settleWithin, withProbeRun } from "../probe/probe-run.js";
import { buildProbeStartInput, type ProbeExtensions } from "../probe/session-config.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

const SENTINEL_TURNS = [
    { toolUses: [{ toolUseId: "toolu_fail_1", toolName: SENTINEL_TOOL_NAME, input: { label: "big" } }] },
    { text: "should not be reached when the hook fails" },
];

interface FailureRunSummary {
    outcome: string;
    requestCount: number;
    sentinelInRequests: boolean;
    sentinelInHistory: boolean;
    sentinelInEvents: boolean;
}

interface HookAttachment {
    hooks?: AgentHooks;
    extensions?: ProbeExtensions;
}

async function runWithHook(
    name: string,
    attachment: HookAttachment,
    hookErrorMode: "ignore" | "throw",
    settleMs: number,
): Promise<FailureRunSummary> {
    let summary: FailureRunSummary | undefined;
    const sessionId = `probe-${name}`;

    await withProbeRun({ name, turns: SENTINEL_TURNS }, async ({ core, scriptedFetch, workspaceDir, coreEvents }) => {
        const startInput = buildProbeStartInput({
            cwd: workspaceDir,
            prompt: "make log",
            extraTools: [createSentinelTool()],
            ...attachment,
            hookErrorMode,
            sessionId,
        });
        const started = core.start(startInput).then(
            (result) => `resolved:${result.result?.finishReason}`,
            (error: unknown) => `rejected:${errorMessage(error)}`,
        );
        const outcome = await settleWithin(started, settleMs, `${name} start`).catch(
            (error: unknown) => `unsettled:${errorMessage(error)}`,
        );
        const history = JSON.stringify(await core.readMessages(sessionId).catch(() => []));

        summary = {
            outcome: outcome.slice(0, 200),
            requestCount: scriptedFetch.capturedRequests.length,
            sentinelInRequests: scriptedFetch.capturedRequests.some((request) =>
                request.bodyText.includes(SENTINEL_MARKER),
            ),
            sentinelInHistory: history.includes(SENTINEL_MARKER),
            sentinelInEvents: coreEvents.some((event) => JSON.stringify(event).includes(SENTINEL_MARKER)),
        };
    });
    if (!summary) {
        throw new Error(`${name} produced no summary`);
    }
    return summary;
}

function buildPointerHooks(failureMode: PointerFailureMode, timeoutMs = 500): AgentHooks {
    const store = new MemoryPointerFixture();
    store.failureMode = failureMode;
    const afterTool = createPointerAfterToolHook(
        { store, workspaceId: "ws_probe", thresholdBytes: 16 * 1024, timeoutMs },
        { replacedCount: 0, passThroughCount: 0 },
    );
    return { afterTool };
}

function asExtension(name: string, hooks: AgentHooks): HookAttachment {
    return { extensions: [{ name, manifest: { capabilities: ["hooks"] }, hooks }] };
}

function holdFor(delayMs: number): AgentHooks {
    return { afterTool: () => new Promise((resolve) => setTimeout(() => resolve(undefined), delayMs)) };
}

function isBlocked(summary: FailureRunSummary): boolean {
    return (
        summary.requestCount === 1 &&
        !summary.sentinelInRequests &&
        !summary.sentinelInHistory &&
        !summary.sentinelInEvents
    );
}

function isFailed(summary: FailureRunSummary): boolean {
    return summary.outcome === "resolved:error" || summary.outcome.startsWith("rejected:");
}

function describe(summary: FailureRunSummary): string {
    return `requests=${summary.requestCount} leak(req/hist/evt)=${summary.sentinelInRequests}/${summary.sentinelInHistory}/${summary.sentinelInEvents} ${summary.outcome}`;
}

export async function runHookFailureScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("hook-failure");

    try {
        const storageError = await runWithHook("hook-throw", { hooks: buildPointerHooks("throw") }, "throw", 8000);
        recorder.check(
            "direct hook: storage failure fails run, no raw fallback",
            isBlocked(storageError) && isFailed(storageError),
            describe(storageError),
        );

        const storageTimeout = await runWithHook("hook-timeout", { hooks: buildPointerHooks("hang") }, "throw", 8000);
        recorder.check(
            "direct hook: storage timeout fails run, no raw fallback",
            isBlocked(storageTimeout) && isFailed(storageTimeout),
            describe(storageTimeout),
        );

        const directIgnore = await runWithHook(
            "hook-direct-ignore",
            { hooks: buildPointerHooks("throw") },
            "ignore",
            8000,
        );
        recorder.check(
            "direct hook errors fail closed even with ignore",
            isBlocked(directIgnore) && isFailed(directIgnore),
            describe(directIgnore),
        );

        const startedAt = Date.now();
        const directHang = await runWithHook("hook-direct-hang", { hooks: holdFor(4500) }, "throw", 10000);
        const directHangMs = Date.now() - startedAt;
        recorder.observe("direct_hook_hang_elapsed_ms", directHangMs);
        recorder.check(
            "direct hook has no SDK timeout (own timeout required)",
            directHangMs >= 4500 && directHang.outcome.includes("completed"),
            describe(directHang),
        );

        const pluginIgnore = await runWithHook(
            "hook-plugin-ignore",
            asExtension("probe-pointer-ignore", buildPointerHooks("throw")),
            "ignore",
            8000,
        );
        recorder.check(
            "object plugin hook errors also fail closed under ignore (differs from docs)",
            isBlocked(pluginIgnore) && isFailed(pluginIgnore),
            describe(pluginIgnore),
        );

        const pluginThrow = await runWithHook(
            "hook-plugin-throw",
            asExtension("probe-pointer-throw", buildPointerHooks("throw")),
            "throw",
            8000,
        );
        recorder.check(
            "plugin hook + throw fails run, no raw fallback",
            isBlocked(pluginThrow) && isFailed(pluginThrow),
            describe(pluginThrow),
        );

        const pluginStartedAt = Date.now();
        const pluginHang = await runWithHook(
            "hook-plugin-hang",
            asExtension("probe-pointer-hang", holdFor(4500)),
            "throw",
            10000,
        );
        const pluginHangMs = Date.now() - pluginStartedAt;
        recorder.observe("plugin_hook_hang_elapsed_ms", pluginHangMs);
        recorder.observe("plugin_hook_hang_summary", pluginHang);
        // Docs state a 3 s hook timeout; 0.2.0 object plugins waited the full 4.5 s, so the app timeout is mandatory.
        recorder.check(
            "object plugin hook has no 3 s SDK timeout (differs from docs)",
            pluginHangMs >= 4500 && pluginHang.outcome.includes("completed"),
            `${describe(pluginHang)} elapsed_ms=${pluginHangMs}`,
        );
    } catch (error) {
        recorder.fail("scenario threw", error);
    }
    return recorder.finish();
}
