/**
 * Runtime Pointer hook registration (4.4). The only afterTool hook the host registers: it maps the
 * SDK result onto the ToolResultTransformer port, so large output is replaced before the SDK
 * persists it or sends it to the model. Use with hookErrorMode "throw" (sessionConfig) so a
 * transformer failure stops the run instead of forwarding the raw output.
 */
import type { AgentHooks } from "@cline/sdk";
import type { ToolResultTransformer } from "../adapter/ports.js";
import { createAfterToolHook } from "../adapter/toolResultHook.js";
import type { ActiveTurn } from "../adapter/turnContext.js";

export function createRuntimePointerHooks(
    transformer: ToolResultTransformer,
    currentTurn: () => ActiveTurn | null,
    timeoutMs: number,
): AgentHooks {
    return { afterTool: createAfterToolHook(transformer, currentTurn, timeoutMs) };
}
