/**
 * Scenario: ClineCore create → subscribe → start → send → abort (mid-request)
 * → send after abort → stop → send after stop is refused → dispose.
 */
import { COMMAND_TOOL_NAME, type CommandToolCounter, createCommandTool } from "../fixtures/probe-tools.js";
import { errorMessage, settleWithin, waitForProbeEvent, withProbeRun } from "../probe/probe-run.js";
import { buildDisabledBuiltinPolicies, buildProbeStartInput } from "../probe/session-config.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

function waitMs(delayMs: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, delayMs));
}

async function runAbortDuringToolCase(recorder: ScenarioRecorder): Promise<void> {
    const counter: CommandToolCounter = { executions: 0 };
    const turns = [
        { toolUses: [{ toolUseId: "toolu_slow_1", toolName: COMMAND_TOOL_NAME, input: { command: "sleep" } }] },
        { text: "unused" },
    ];
    const toolPolicies = {
        ...buildDisabledBuiltinPolicies(),
        [COMMAND_TOOL_NAME]: { enabled: true, autoApprove: true },
    };
    const sessionId = "probe-abort-during-tool";

    await withProbeRun({ name: "lifecycle-abort-tool", turns }, async ({ core, scriptedFetch, workspaceDir }) => {
        const extraTools = [createCommandTool(counter, 3000)];
        const started = core.start(
            buildProbeStartInput({ cwd: workspaceDir, prompt: "slow", extraTools, toolPolicies, sessionId }),
        );
        await waitForProbeEvent(() => counter.executions > 0, started, "tool execution");
        const abortedAt = Date.now();
        await core.abort(sessionId, "probe abort during tool");
        const outcome = await settleWithin(
            started.then(
                (result) => `resolved:${result.result?.finishReason}`,
                (error: unknown) => `rejected:${errorMessage(error)}`,
            ),
            5000,
            "abort during tool",
        );
        const elapsedMs = Date.now() - abortedAt;

        recorder.check(
            "abort during tool signals the tool and ends run",
            counter.abortedExecutions === 1 && /abort/i.test(outcome) && elapsedMs < 2000,
            `aborted_tools=${counter.abortedExecutions ?? 0} ${outcome} elapsed_ms=${elapsedMs}`,
        );
        recorder.check(
            "no provider request after aborted tool",
            scriptedFetch.capturedRequests.length === 1,
            `requests=${scriptedFetch.capturedRequests.length}`,
        );
    });
}

export async function runLifecycleScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("lifecycle");
    const turns = [
        { text: "first answer" },
        { text: "second answer" },
        { holdUntilAborted: true },
        { text: "after abort" },
    ];

    try {
        await withProbeRun({ name: "lifecycle", turns }, async ({ core, scriptedFetch, workspaceDir, coreEvents }) => {
            const started = await core.start(
                buildProbeStartInput({ cwd: workspaceDir, prompt: "hello", extraTools: [], interactive: true }),
            );
            const sessionId = started.sessionId;
            recorder.check(
                "start returned session and first result",
                sessionId.length > 0 && started.result?.text === "first answer",
                `finish=${started.result?.finishReason}`,
            );

            const sent = await core.send({ sessionId, prompt: "second" });
            recorder.check("send ran a second turn", sent?.text === "second answer", `finish=${sent?.finishReason}`);

            const heldTurn = core.send({ sessionId, prompt: "third (will be aborted)" });
            await waitMs(300);
            await core.abort(sessionId, "probe abort");
            const abortedOutcome = await settleWithin(
                heldTurn.then(
                    (result) => `resolved:${result?.finishReason}`,
                    (error: unknown) => `rejected:${errorMessage(error)}`,
                ),
                5000,
                "aborted send",
            );
            recorder.check(
                "abort ended the in-flight turn",
                /aborted|abort/i.test(abortedOutcome),
                abortedOutcome.slice(0, 160),
            );

            const afterAbort = await core.send({ sessionId, prompt: "fourth" });
            recorder.check(
                "session usable after abort",
                afterAbort?.text === "after abort",
                `finish=${afterAbort?.finishReason}`,
            );

            await core.stop(sessionId);
            const afterStop = await core.send({ sessionId, prompt: "fifth" }).then(
                () => "accepted",
                (error: unknown) => `refused:${errorMessage(error)}`,
            );
            recorder.check("send after stop is refused", afterStop.startsWith("refused"), afterStop.slice(0, 160));
            recorder.check(
                "provider requests match turns",
                scriptedFetch.capturedRequests.length === 4,
                `requests=${scriptedFetch.capturedRequests.length}`,
            );

            const eventTypes = [...new Set(coreEvents.map((event) => event.type))].sort();
            recorder.check("subscribe delivered core events", eventTypes.length > 0, eventTypes.join(","));
            recorder.observe("core_event_types", eventTypes);
            recorder.observe("aborted_outcome", abortedOutcome.slice(0, 200));
        });
        recorder.check("dispose completed", true, "ClineCore.dispose resolved");
        await runAbortDuringToolCase(recorder);
    } catch (error) {
        recorder.fail("scenario threw", error);
    }
    return recorder.finish();
}
