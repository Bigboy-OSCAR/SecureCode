/**
 * Shared ClineCore start input used by every scenario. All safety-relevant
 * switches are explicit so a scenario only overrides what it is testing.
 */
import type { AgentHooks, AgentTool, ClineCoreStartInput, ToolPolicy } from "@cline/sdk";

export const PROBE_PROVIDER_ID = "anthropic";
export const PROBE_MODEL_ID = "claude-sonnet-5-5";

/** Built-in tool names declared by @cline/core 0.2.0 `DefaultToolNames`. */
export const BUILTIN_TOOL_NAMES = [
    "read_files",
    "search_codebase",
    "run_commands",
    "fetch_web_content",
    "apply_patch",
    "editor",
    "skills",
    "ask_question",
    "submit_and_exit",
] as const;

export interface ProbeSessionOptions {
    cwd: string;
    prompt: string;
    extraTools: AgentTool[];
    hooks?: AgentHooks;
    /** Object-form plugins; their hooks run through the SDK's guarded plugin path. */
    extensions?: ProbeExtensions;
    enableTools?: boolean;
    /** true keeps the session open for `send`; false ends it after the start run. */
    interactive?: boolean;
    /** Host-owned session id, so abort can target a run before start() resolves. */
    sessionId?: string;
    /** Defaults to "throw"; "ignore" is only used to demonstrate the leak it causes. */
    hookErrorMode?: "ignore" | "throw";
    toolPolicies?: Record<string, ToolPolicy>;
    /** Spy passed as `checkpoint.createCheckpoint` while `enabled` stays false. */
    checkpointSpy?: CheckpointCreator;
}

export type ProbeExtensions = NonNullable<ClineCoreStartInput["config"]["extensions"]>;
type CheckpointCreator = NonNullable<NonNullable<ClineCoreStartInput["config"]["checkpoint"]>["createCheckpoint"]>;

/** Disables every built-in tool so only project-owned tools stay visible. */
export function buildDisabledBuiltinPolicies(): Record<string, ToolPolicy> {
    const policies: Record<string, ToolPolicy> = {};
    for (const toolName of BUILTIN_TOOL_NAMES) {
        policies[toolName] = { enabled: false };
    }
    return policies;
}

export function buildProbeStartInput(options: ProbeSessionOptions): ClineCoreStartInput {
    const toolPolicies = options.toolPolicies ?? buildDisabledBuiltinPolicies();

    return {
        prompt: options.prompt,
        interactive: options.interactive ?? false,
        toolPolicies,
        config: {
            ...(options.sessionId ? { sessionId: options.sessionId } : {}),
            providerId: PROBE_PROVIDER_ID,
            modelId: PROBE_MODEL_ID,
            // Fixture credential; the scripted fetch never forwards it anywhere.
            apiKey: "fixture-not-a-secret",
            cwd: options.cwd,
            workspaceRoot: options.cwd,
            mode: "act",
            systemPrompt: "You are the SecureCode SDK probe. Use only the provided tools.",
            maxIterations: 6,
            maxTokensPerTurn: 1024,
            // false removes built-in tools AND the provider web_search tool; extraTools stay.
            enableTools: options.enableTools ?? false,
            enableSpawnAgent: false,
            enableAgentTeams: false,
            disableMcpSettingsTools: true,
            mcpApps: false,
            yolo: false,
            toolPolicies,
            hookErrorMode: options.hookErrorMode ?? "throw",
            checkpoint: { enabled: false, ...(options.checkpointSpy ? { createCheckpoint: options.checkpointSpy } : {}) },
            compaction: { enabled: false },
            extraTools: options.extraTools,
            ...(options.hooks ? { hooks: options.hooks } : {}),
            ...(options.extensions ? { extensions: options.extensions } : {}),
        },
        localRuntime: {
            // Do not load user/global rules, skills, workflows, plugins or file hooks.
            configExtensions: [],
        },
    };
}
