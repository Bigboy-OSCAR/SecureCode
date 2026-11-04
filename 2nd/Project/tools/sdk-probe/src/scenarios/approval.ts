/**
 * Scenario: `toolPolicies.autoApprove: false` routes a project command tool to
 * `capabilities.requestToolApproval`. Covers reject, approve, timeout, and
 * abort-while-pending — first raw SDK behaviour, then the app broker fix.
 */
import type { ToolApprovalRequest, ToolApprovalResult, ToolPolicy } from "@cline/sdk";
import type { ScriptedTurn } from "../fixtures/anthropic-sse.js";
import { COMMAND_TOOL_NAME, type CommandToolCounter, createCommandTool } from "../fixtures/probe-tools.js";
import { ApprovalBroker, digestToolInput } from "../probe/approval-broker.js";
import { errorMessage, settleWithin, withProbeRun } from "../probe/probe-run.js";
import { buildDisabledBuiltinPolicies, buildProbeStartInput } from "../probe/session-config.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

const USER_REJECTION_REASON = "This tool call was rejected by the user and not executed.";

function buildCommandTurns(): ScriptedTurn[] {
    return [
        { toolUses: [{ toolUseId: "toolu_cmd_1", toolName: COMMAND_TOOL_NAME, input: { command: "echo fixture" } }] },
        { text: "acknowledged" },
    ];
}

function buildApprovalPolicies(): Record<string, ToolPolicy> {
    return { ...buildDisabledBuiltinPolicies(), [COMMAND_TOOL_NAME]: { enabled: true, autoApprove: false } };
}

function waitMs(delayMs: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, delayMs));
}

async function waitForTicket(broker: ApprovalBroker): Promise<void> {
    for (let attempt = 0; attempt < 100 && broker.tickets.length === 0; attempt += 1) {
        await waitMs(50);
    }
}

async function runRejectCase(recorder: ScenarioRecorder): Promise<void> {
    const counter: CommandToolCounter = { executions: 0 };
    const approvalRequests: ToolApprovalRequest[] = [];
    const requestToolApproval = async (request: ToolApprovalRequest): Promise<ToolApprovalResult> => {
        approvalRequests.push(request);
        return { approved: false, reason: USER_REJECTION_REASON };
    };

    await withProbeRun(
        { name: "approval-reject", turns: buildCommandTurns(), requestToolApproval },
        async ({ core, scriptedFetch, workspaceDir }) => {
            await core.start(
                buildProbeStartInput({
                    cwd: workspaceDir,
                    prompt: "run it",
                    extraTools: [createCommandTool(counter)],
                    toolPolicies: buildApprovalPolicies(),
                }),
            );
            const request = approvalRequests[0];
            const secondBody = scriptedFetch.capturedRequests[1]?.bodyText ?? "";

            recorder.check(
                "approval requested once",
                approvalRequests.length === 1,
                `requests=${approvalRequests.length}`,
            );
            recorder.check(
                "approval carries ids and input",
                request?.toolName === COMMAND_TOOL_NAME &&
                    request.toolCallId === "toolu_cmd_1" &&
                    request.sessionId.length > 0,
                "toolName/toolCallId/sessionId/input present",
            );
            recorder.check("rejected tool not executed", counter.executions === 0, `executions=${counter.executions}`);
            recorder.check(
                "rejection reaches model as error tool_result",
                secondBody.includes(USER_REJECTION_REASON) && secondBody.includes('"is_error":true'),
                "request#2 has is_error tool_result",
            );
        },
    );
}

async function runApproveCase(recorder: ScenarioRecorder): Promise<void> {
    const counter: CommandToolCounter = { executions: 0 };
    const broker = new ApprovalBroker(5000);

    await withProbeRun(
        { name: "approval-approve", turns: buildCommandTurns(), requestToolApproval: broker.requestToolApproval },
        async ({ core, workspaceDir }) => {
            const started = core.start(
                buildProbeStartInput({
                    cwd: workspaceDir,
                    prompt: "run it",
                    extraTools: [createCommandTool(counter)],
                    toolPolicies: buildApprovalPolicies(),
                }),
            );
            await waitForTicket(broker);
            const ticket = broker.tickets[0];
            const mismatch = broker.decide(ticket?.approvalId ?? "", "wrong-digest", true);
            const applied = broker.decide(ticket?.approvalId ?? "", digestToolInput({ command: "echo fixture" }), true);
            await settleWithin(started, 5000, "approved start");

            recorder.check("digest mismatch refused", mismatch === "digest_mismatch", mismatch);
            recorder.check(
                "approved tool executed once",
                applied === "applied" && counter.executions === 1,
                `outcome=${applied} executions=${counter.executions}`,
            );
        },
    );
}

async function runTimeoutCase(recorder: ScenarioRecorder): Promise<void> {
    const counter: CommandToolCounter = { executions: 0 };
    const broker = new ApprovalBroker(300);

    await withProbeRun(
        { name: "approval-timeout", turns: buildCommandTurns(), requestToolApproval: broker.requestToolApproval },
        async ({ core, workspaceDir }) => {
            await settleWithin(
                core.start(
                    buildProbeStartInput({
                        cwd: workspaceDir,
                        prompt: "run it",
                        extraTools: [createCommandTool(counter)],
                        toolPolicies: buildApprovalPolicies(),
                    }),
                ),
                5000,
                "timeout start",
            );
            const late = broker.decide(
                broker.tickets[0]?.approvalId ?? "",
                digestToolInput({ command: "echo fixture" }),
                true,
            );
            recorder.check(
                "approval timeout rejects and late decision refused",
                counter.executions === 0 && late === "unknown_or_settled",
                `executions=${counter.executions} late=${late}`,
            );
        },
    );
}

/** Raw SDK: abort does not settle the pending approval; a late "approved" still runs the tool. */
async function runRawAbortCase(recorder: ScenarioRecorder): Promise<void> {
    const counter: CommandToolCounter = { executions: 0 };
    let resolveLate: ((result: ToolApprovalResult) => void) | undefined;
    const requestToolApproval = (): Promise<ToolApprovalResult> =>
        new Promise((resolve) => {
            resolveLate = resolve;
        });
    const sessionId = "probe-approval-raw-abort";

    await withProbeRun(
        { name: "approval-raw-abort", turns: buildCommandTurns(), requestToolApproval },
        async ({ core, workspaceDir }) => {
            const started = core.start(
                buildProbeStartInput({
                    cwd: workspaceDir,
                    prompt: "run it",
                    extraTools: [createCommandTool(counter)],
                    toolPolicies: buildApprovalPolicies(),
                    sessionId,
                }),
            );
            while (!resolveLate) {
                await waitMs(50);
            }
            await core.abort(sessionId, "probe abort while approval pending");
            await waitMs(500);
            const settledBeforeLateApproval = await Promise.race([
                started.then(
                    () => true,
                    () => true,
                ),
                waitMs(100).then(() => false),
            ]);
            resolveLate({ approved: true });
            await settleWithin(
                started.catch((error: unknown) => errorMessage(error)),
                5000,
                "raw abort start",
            );

            recorder.observe("raw_sdk_run_settled_before_late_approval", settledBeforeLateApproval);
            recorder.observe("raw_sdk_tool_executions_after_abort_then_late_approval", counter.executions);
            recorder.check(
                "raw SDK gap reproduced (abort leaves approval pending)",
                !settledBeforeLateApproval && counter.executions === 1,
                `settled_before_late=${settledBeforeLateApproval} executions=${counter.executions}`,
            );
        },
    );
}

/** Mitigation: host cancels broker approvals for the session before calling abort. */
async function runBrokerAbortCase(recorder: ScenarioRecorder): Promise<void> {
    const counter: CommandToolCounter = { executions: 0 };
    const broker = new ApprovalBroker(10000);
    const sessionId = "probe-approval-broker-abort";

    await withProbeRun(
        { name: "approval-broker-abort", turns: buildCommandTurns(), requestToolApproval: broker.requestToolApproval },
        async ({ core, workspaceDir }) => {
            const started = core.start(
                buildProbeStartInput({
                    cwd: workspaceDir,
                    prompt: "run it",
                    extraTools: [createCommandTool(counter)],
                    toolPolicies: buildApprovalPolicies(),
                    sessionId,
                }),
            );
            await waitForTicket(broker);
            const cancelled = broker.cancelSession(sessionId, "run cancelled");
            await core.abort(sessionId, "probe abort while approval pending");
            const outcome = await settleWithin(
                started.then(
                    (result) => `resolved:${result.result?.finishReason}`,
                    (error: unknown) => `rejected:${errorMessage(error)}`,
                ),
                5000,
                "broker abort start",
            );
            const late = broker.decide(
                broker.tickets[0]?.approvalId ?? "",
                digestToolInput({ command: "echo fixture" }),
                true,
            );
            await waitMs(200);

            recorder.check(
                "broker cancel + abort ends run",
                cancelled === 1 && /abort/i.test(outcome),
                `cancelled=${cancelled} ${outcome.slice(0, 120)}`,
            );
            recorder.check(
                "late approval after cancel refused, tool not run",
                late === "unknown_or_settled" && counter.executions === 0,
                `late=${late} executions=${counter.executions}`,
            );
        },
    );
}

export async function runApprovalScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("approval");
    const cases: Array<[string, (target: ScenarioRecorder) => Promise<void>]> = [
        ["reject", runRejectCase],
        ["approve", runApproveCase],
        ["timeout", runTimeoutCase],
        ["raw-abort", runRawAbortCase],
        ["broker-abort", runBrokerAbortCase],
    ];

    for (const [caseName, runCase] of cases) {
        try {
            await runCase(recorder);
        } catch (error) {
            recorder.fail(`${caseName} case threw`, error);
        }
    }
    return recorder.finish();
}
