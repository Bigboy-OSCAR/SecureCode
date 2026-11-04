/**
 * Scenario: fixed tool allow-list. Checks which tools reach the provider under
 * each setting, that a call to a hidden built-in never executes, and that
 * `capabilities.toolExecutors` replaces a built-in executor (read_files).
 */
import { setModelToolEnabledGlobally, type ToolPolicy } from "@cline/sdk";
import { createSentinelTool } from "../fixtures/probe-tools.js";
import { withProbeRun } from "../probe/probe-run.js";
import { buildDisabledBuiltinPolicies, buildProbeStartInput } from "../probe/session-config.js";
import { listToolNames } from "../support/payload-inspect.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

const WRAPPED_READ_MARKER = "SECURECODE_WRAPPED_READ";
const FORBIDDEN_TOOL_PATTERN = /web_search|image_generation|spawn|team|mcp|skills/;

interface ExecutorCounters {
    bash: number;
    readFile: number;
}

function buildCountingExecutors(counters: ExecutorCounters) {
    return {
        bash: async () => {
            counters.bash += 1;
            return "bash executor must not run";
        },
        readFile: async () => {
            counters.readFile += 1;
            return `${WRAPPED_READ_MARKER} bounded fixture content`;
        },
    };
}

async function captureToolNames(
    name: string,
    enableTools: boolean,
    toolPolicies: Record<string, ToolPolicy>,
): Promise<string[]> {
    let toolNames: string[] = [];
    await withProbeRun({ name, turns: [{ text: "ok" }] }, async ({ core, scriptedFetch, workspaceDir }) => {
        await core.start(
            buildProbeStartInput({
                cwd: workspaceDir,
                prompt: "list",
                extraTools: [createSentinelTool()],
                enableTools,
                toolPolicies,
            }),
        );
        const firstRequest = scriptedFetch.capturedRequests[0];
        toolNames = firstRequest ? listToolNames(firstRequest) : [];
    });
    return toolNames;
}

async function runHiddenBuiltinCallCase(recorder: ScenarioRecorder): Promise<void> {
    const counters: ExecutorCounters = { bash: 0, readFile: 0 };
    const turns = [
        { toolUses: [{ toolUseId: "toolu_hidden_1", toolName: "run_commands", input: { commands: ["git status"] } }] },
        { text: "ok" },
    ];

    await withProbeRun(
        { name: "tool-hidden-call", turns, toolExecutors: buildCountingExecutors(counters) },
        async ({ core, scriptedFetch, workspaceDir }) => {
            await core.start(
                buildProbeStartInput({ cwd: workspaceDir, prompt: "try hidden", extraTools: [createSentinelTool()] }),
            );
            const secondBody = scriptedFetch.capturedRequests[1]?.bodyText ?? "";
            recorder.check(
                "call to hidden run_commands never executes",
                counters.bash === 0 && secondBody.includes('"is_error":true'),
                `bash_calls=${counters.bash} error_result=${secondBody.includes('"is_error":true')}`,
            );
        },
    );
}

async function runReplacedReadCase(recorder: ScenarioRecorder): Promise<void> {
    const counters: ExecutorCounters = { bash: 0, readFile: 0 };
    const policies: Record<string, ToolPolicy> = {
        ...buildDisabledBuiltinPolicies(),
        read_files: { enabled: true, autoApprove: true },
    };
    const turns = [
        { toolUses: [{ toolUseId: "toolu_read_1", toolName: "read_files", input: { files: [{ path: "app.py" }] } }] },
        { text: "ok" },
    ];

    await withProbeRun(
        { name: "tool-replaced-read", turns, toolExecutors: buildCountingExecutors(counters) },
        async ({ core, scriptedFetch, workspaceDir }) => {
            await core.start(
                buildProbeStartInput({
                    cwd: workspaceDir,
                    prompt: "read",
                    extraTools: [],
                    enableTools: true,
                    toolPolicies: policies,
                }),
            );
            const [firstRequest, secondRequest] = scriptedFetch.capturedRequests;
            const toolNames = firstRequest ? listToolNames(firstRequest) : [];
            recorder.check(
                "read_files executor replaced by app wrapper",
                counters.readFile === 1 && (secondRequest?.bodyText.includes(WRAPPED_READ_MARKER) ?? false),
                `wrapper_calls=${counters.readFile}`,
            );
            recorder.check(
                "only allow-listed built-in exposed",
                toolNames.join("|") === "read_files",
                `tools=${toolNames.join("|")}`,
            );
        },
    );
}

export async function runToolRestrictionScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("tool-restriction");

    try {
        const recommended = await captureToolNames("tool-recommended", false, buildDisabledBuiltinPolicies());
        recorder.check(
            "enableTools=false exposes only project tools",
            recommended.join("|") === "probe_generate_log",
            `tools=${recommended.join("|")}`,
        );

        const policiesOnly = await captureToolNames("tool-policies-only", true, buildDisabledBuiltinPolicies());
        recorder.observe("enable_tools_true_with_disabled_policies", policiesOnly);
        recorder.check(
            "policies alone keep provider web_search (finding)",
            policiesOnly.includes("web_search"),
            `tools=${policiesOnly.join("|")}`,
        );

        const unrestricted = await captureToolNames("tool-unrestricted", true, {});
        recorder.observe("enable_tools_true_without_policies", unrestricted);
        recorder.check(
            "no spawn/team/mcp/skills tools when disabled in config",
            !unrestricted.some((name) => /spawn|team|mcp|skills/.test(name)),
            `tools=${unrestricted.join("|")}`,
        );

        await runHiddenBuiltinCallCase(recorder);

        // Isolated probe CLINE_DIR only: the global model-tool switch also removes web_search.
        setModelToolEnabledGlobally("web_search", false);
        await runReplacedReadCase(recorder);
        const globalOff = await captureToolNames("tool-global-websearch-off", true, buildDisabledBuiltinPolicies());
        recorder.check(
            "global web_search off removes provider tool",
            !globalOff.some((name) => FORBIDDEN_TOOL_PATTERN.test(name)),
            `tools=${globalOff.join("|")}`,
        );
        setModelToolEnabledGlobally("web_search", true);
    } catch (error) {
        recorder.fail("scenario threw", error);
    }
    return recorder.finish();
}
