/**
 * Explicit toolPolicies for every tool name the SDK knows (3.1 C-04). Built-in
 * tools and provider tools are disabled; project tools are enabled and only
 * read-only ones auto-approve. No tool relies on the SDK's default policy.
 */
export interface ToolPolicyEntry {
    enabled: boolean;
    autoApprove: boolean;
}

/** @cline/core 0.2.0 DefaultToolNames plus provider-executed tools. */
export const SDK_BUILTIN_TOOL_NAMES = [
    "read_files",
    "search_codebase",
    "run_commands",
    "fetch_web_content",
    "apply_patch",
    "editor",
    "skills",
    "ask_question",
    "submit_and_exit",
    "web_search",
    "image_generation",
] as const;

export interface ProjectToolPolicy {
    name: string;
    requiresApproval: boolean;
}

export function buildToolPolicies(projectTools: readonly ProjectToolPolicy[]): Record<string, ToolPolicyEntry> {
    const policies: Record<string, ToolPolicyEntry> = {};
    for (const name of SDK_BUILTIN_TOOL_NAMES) {
        policies[name] = { enabled: false, autoApprove: false };
    }
    for (const tool of projectTools) {
        if (tool.name in policies) throw new Error(`project tool ${tool.name} shadows an SDK tool`);
        policies[tool.name] = { enabled: true, autoApprove: !tool.requiresApproval };
    }
    return policies;
}
