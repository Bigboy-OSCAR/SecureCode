/**
 * afterTool hook that replaces oversized local tool results with a pointer
 * descriptor. Storage failure or timeout throws, and with
 * `hookErrorMode: "throw"` the run fails instead of forwarding the original.
 */
import type { AgentHooks } from "@cline/sdk";
import type { MemoryPointerFixture } from "../fixtures/memory-pointer-fixture.js";
import { settleWithin } from "./probe-run.js";

type AfterToolHook = NonNullable<AgentHooks["afterTool"]>;

export interface PointerHookOptions {
    store: MemoryPointerFixture;
    workspaceId: string;
    thresholdBytes: number;
    timeoutMs: number;
}

export interface PointerHookStats {
    replacedCount: number;
    passThroughCount: number;
}

function serializeOutput(output: unknown): string {
    return typeof output === "string" ? output : JSON.stringify(output);
}

export function createPointerAfterToolHook(options: PointerHookOptions, stats: PointerHookStats): AfterToolHook {
    return async (context) => {
        const serialized = serializeOutput(context.result.output);
        if (Buffer.byteLength(serialized, "utf8") <= options.thresholdBytes) {
            stats.passThroughCount += 1;
            return undefined;
        }

        const sessionId = context.snapshot.conversationId ?? "unknown-session";
        const storing = options.store.put(serialized, options.workspaceId, sessionId);
        const descriptor = await settleWithin(storing, options.timeoutMs, "pointer hook store");
        stats.replacedCount += 1;
        return {
            result: {
                output: descriptor,
                isError: context.result.isError ?? false,
                metadata: { securecode_pointerized: true },
            },
        };
    };
}
