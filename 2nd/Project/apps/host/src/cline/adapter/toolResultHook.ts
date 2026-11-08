/**
 * Maps the SDK afterTool hook onto the ToolResultTransformer port (4.4 owns the
 * policy). The hook runs before the result is persisted or sent to the model;
 * any transformer failure or timeout throws, and with hookErrorMode "throw" the
 * run fails instead of forwarding raw output (3.1 S-04, C-08).
 */
import type { AgentHooks } from "@cline/sdk";
import type { ToolResultTransformer } from "./ports.js";
import { recordFailure, type ActiveTurn } from "./turnContext.js";

type AfterToolHook = NonNullable<AgentHooks["afterTool"]>;

function serializeOutput(output: unknown): string {
    if (typeof output === "string") return output;
    const text = JSON.stringify(output);
    if (typeof text !== "string") throw new Error("tool output cannot be serialized");
    return text;
}

function withTimeout<T>(work: Promise<T>, timeoutMs: number, controller: AbortController): Promise<T> {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            controller.abort(new Error("tool result transformer timed out"));
            reject(new Error("tool result transformer timed out"));
        }, timeoutMs);
        work.then(
            (value) => {
                clearTimeout(timer);
                resolve(value);
            },
            (error: unknown) => {
                clearTimeout(timer);
                reject(error instanceof Error ? error : new Error("tool result transformer failed"));
            },
        );
    });
}

export function createAfterToolHook(
    transformer: ToolResultTransformer,
    currentTurn: () => ActiveTurn | null,
    timeoutMs: number,
): AfterToolHook {
    return async ({ toolCall, result }) => {
        const turn = currentTurn();
        if (!turn) throw new Error("tool result arrived outside an active run");
        const output = serializeOutput(result.output);
        const outputBytes = Buffer.byteLength(output, "utf8");
        const controller = new AbortController();
        let transformed;
        try {
            transformed = await withTimeout(
                transformer.transform(
                    {
                        workspaceId: turn.workspaceId,
                        sessionId: turn.sessionId,
                        runId: turn.runId,
                        toolCallId: toolCall.toolCallId,
                        toolName: toolCall.toolName,
                        output,
                        outputBytes,
                        preLimitedByExecutor: false,
                    },
                    controller.signal,
                ),
                timeoutMs,
                controller,
            );
        } catch (error) {
            recordFailure(turn, {
                code: "SERVICE_UNAVAILABLE",
                message: "the tool result could not be stored safely; the run was stopped",
            });
            throw error;
        }
        const info = { outputBytes, ...(transformed.kind === "pointer" ? { pointer: transformed.pointer } : {}) };
        turn.toolOutputs.set(toolCall.toolCallId, info);
        if (transformed.kind === "pointer") {
            turn.listener({
                kind: "pointer_created",
                toolCallId: toolCall.toolCallId,
                pointer: transformed.pointer,
                byteSize: transformed.byteSize,
            });
        }
        return {
            result: {
                output: transformed.text,
                isError: result.isError ?? false,
                metadata: { securecode_transformed: transformed.kind },
            },
        };
    };
}
