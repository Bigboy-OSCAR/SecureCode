/**
 * Scenario: `hooks.beforeModel` observes request messages/tools/options, can
 * remove a tool, can project messages, and can stop before any provider call.
 * Compares the beforeModel view with the final outbound bytes to show that
 * provider framing is added after the hook.
 */
import type { AgentHooks } from "@cline/sdk";
import { COMMAND_TOOL_NAME, createCommandTool, createSentinelTool, SENTINEL_TOOL_NAME } from "../fixtures/probe-tools.js";
import { withProbeRun } from "../probe/probe-run.js";
import { buildDisabledBuiltinPolicies, buildProbeStartInput } from "../probe/session-config.js";
import { isToolPairingPreserved, listToolNames } from "../support/payload-inspect.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

type BeforeModelContext = Parameters<NonNullable<AgentHooks["beforeModel"]>>[0];

interface ModelViewRecord {
    messageRoles: string[];
    partTypes: string[];
    toolNames: string[];
    optionKeys: string[];
    viewBytes: number;
}

const PROJECTION_MARKER = "PROJECTED_BY_BEFORE_MODEL";
const PROJECTED_MAX_TOKENS = 321;

function recordView(context: BeforeModelContext): ModelViewRecord {
    const { request } = context;
    const view = { systemPrompt: request.systemPrompt, messages: request.messages, tools: request.tools };
    return {
        messageRoles: request.messages.map((message) => message.role),
        partTypes: request.messages.flatMap((message) => message.content.map((part) => part.type)),
        toolNames: request.tools.map((tool) => tool.name),
        optionKeys: Object.keys(request.options ?? {}).sort(),
        viewBytes: Buffer.byteLength(JSON.stringify(view), "utf8"),
    };
}

async function runObserveAndModifyCase(recorder: ScenarioRecorder): Promise<void> {
    const views: ModelViewRecord[] = [];
    const beforeModel: NonNullable<AgentHooks["beforeModel"]> = (context) => {
        views.push(recordView(context));
        const tools = context.request.tools.filter((tool) => tool.name !== COMMAND_TOOL_NAME);
        const firstMessage = context.request.messages[0];
        // Project only the first user text for this provider call; the canonical transcript must stay unchanged.
        const projected = firstMessage
            ? [{ ...firstMessage, content: [{ type: "text" as const, text: PROJECTION_MARKER }] }, ...context.request.messages.slice(1)]
            : context.request.messages;
        const options = { ...context.request.options, maxTokensPerTurn: PROJECTED_MAX_TOKENS };
        return { tools, messages: projected, options };
    };
    const turns = [
        { toolUses: [{ toolUseId: "toolu_bm_1", toolName: SENTINEL_TOOL_NAME, input: { label: "small" } }] },
        { text: "done" },
    ];

    await withProbeRun({ name: "before-model-observe", turns }, async ({ core, scriptedFetch, workspaceDir }) => {
        const policies = { ...buildDisabledBuiltinPolicies(), [COMMAND_TOOL_NAME]: { enabled: true, autoApprove: true } };
        const sessionId = "probe-before-model";
        const extraTools = [createSentinelTool(), createCommandTool({ executions: 0 })];
        await core.start(buildProbeStartInput({ cwd: workspaceDir, prompt: "original prompt", extraTools, toolPolicies: policies, hooks: { beforeModel }, sessionId }));
        const [firstRequest, secondRequest] = scriptedFetch.capturedRequests;
        const history = JSON.stringify(await core.readMessages(sessionId));

        recorder.check("beforeModel saw messages/tools each call", views.length === 2 && (views[0]?.toolNames.includes(COMMAND_TOOL_NAME) ?? false), `calls=${views.length} tools=${views[0]?.toolNames.join("|")}`);
        recorder.check("beforeModel saw tool-call then tool-result order", views[1]?.partTypes.join(",") === "text,tool-call,tool-result", `parts#2=${views[1]?.partTypes.join(",")} roles=${views[1]?.messageRoles.join(",")}`);
        recorder.check("tool removal reached outbound payload", firstRequest !== undefined && !listToolNames(firstRequest).includes(COMMAND_TOOL_NAME), `outbound tools=${firstRequest ? listToolNames(firstRequest).join("|") : ""}`);
        // 0.2.0 Core adapter takes max_tokens from session config; beforeModel options do not override it.
        recorder.check("beforeModel options.maxTokensPerTurn not applied outbound (finding)", firstRequest?.body.max_tokens === 1024, `outbound max_tokens=${String(firstRequest?.body.max_tokens)} requested=${PROJECTED_MAX_TOKENS}`);
        recorder.check("message projection reached outbound payload", firstRequest?.bodyText.includes(PROJECTION_MARKER) ?? false, "projection marker in request#1");
        recorder.check("projection did not rewrite canonical history", history.includes("original prompt") && !history.includes(PROJECTION_MARKER), "readMessages keeps original prompt");
        recorder.check("outbound tool pairing preserved", secondRequest !== undefined && isToolPairingPreserved(secondRequest), "request#2 pairing");

        const framing = views.map((view, index) => ({ before_model_view_bytes: view.viewBytes, outbound_body_bytes: scriptedFetch.capturedRequests[index]?.bodyBytes ?? 0 }));
        recorder.observe("framing_bytes", framing);
        recorder.observe("before_model_option_keys", views[0]?.optionKeys ?? []);
        const sdkTruncated = secondRequest?.bodyText.includes("...[truncated ") ?? false;
        recorder.check("SDK truncates >8000-char tool result after beforeModel (finding)", sdkTruncated && (views[1]?.viewBytes ?? 0) > 64 * 1024, `view#2=${views[1]?.viewBytes} outbound#2=${secondRequest?.bodyBytes}`);
        recorder.check("outbound size differs from beforeModel view", framing.every((entry) => entry.before_model_view_bytes !== entry.outbound_body_bytes), JSON.stringify(framing));
    });
}

async function runStopCase(recorder: ScenarioRecorder): Promise<void> {
    const beforeModel: NonNullable<AgentHooks["beforeModel"]> = () => ({ stop: true, reason: "BUDGET_EXCEEDED: probe cap" });

    await withProbeRun({ name: "before-model-stop", turns: [{ text: "must not be requested" }] }, async ({ core, scriptedFetch, workspaceDir }) => {
        const started = await core.start(buildProbeStartInput({ cwd: workspaceDir, prompt: "hello", extraTools: [], hooks: { beforeModel } }));
        recorder.check("beforeModel stop sends no provider request", scriptedFetch.capturedRequests.length === 0, `requests=${scriptedFetch.capturedRequests.length} finish=${started.result?.finishReason}`);
        recorder.observe("stop_finish_reason", started.result?.finishReason ?? "<none>");
    });
}

export async function runBeforeModelScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("before-model");
    const cases: Array<[string, (target: ScenarioRecorder) => Promise<void>]> = [
        ["observe-and-modify", runObserveAndModifyCase],
        ["stop", runStopCase],
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
