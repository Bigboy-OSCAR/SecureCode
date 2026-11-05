/** Transform actual SDK tool results in afterTool, before persistence. Configure the SDK with hookErrorMode: "throw". */
import type { AgentHooks, AgentPlugin } from "@cline/sdk";
import { storeRuntimePointer, type RuntimePointerHookOptions } from "../../pointer-hooks/runtimePointerHook.js";

export function createRuntimePointerPlugin(options: RuntimePointerHookOptions): AgentPlugin {
    // SDK conversationId is generated independently of the host session id. Scope this
    // plugin instance to one start() call and use its authenticated host context.
    const scope = { ...options };
    const afterTool: NonNullable<AgentHooks["afterTool"]> = async ({ result }) => {
        const content = typeof result.output === "string" ? result.output : JSON.stringify(result.output);
        if (typeof content !== "string") throw new Error("tool output cannot be serialized");
        const stored = await storeRuntimePointer({ content }, scope);
        if (!stored.stored) return undefined;
        return {
            result: {
                output: { kind: "runtime", pointer: stored.pointerUri, byte_size: stored.byteSize },
                isError: result.isError ?? false,
                metadata: { securecode_pointerized: true },
            },
        };
    };
    return { name: "securecode-runtime-pointer", manifest: { capabilities: ["hooks"] }, hooks: { afterTool } };
}
