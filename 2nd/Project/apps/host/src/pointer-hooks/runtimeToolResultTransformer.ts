/** Replace large tool output with a Runtime Pointer descriptor before it reaches the model or history. */
import type { ToolResultInput, ToolResultOutput, ToolResultTransformer } from "../cline/adapter/ports.js";
import { describeStoredOutput } from "./runtimeDescriptor.js";
import { storeRuntimePointer, type RuntimePointerHookOptions } from "./runtimePointerHook.js";

export const DEFAULT_THRESHOLD_BYTES = 4096;
export const BOUNDED_READ_MAX_BYTES = 32 * 1024;
const MAX_THRESHOLD_BYTES = 32 * 1024 * 1024;
const BOUNDED_READ_TOOLS: ReadonlySet<string> = new Set([
    "runtime_read",
    "runtime_search",
    "source_read",
    "source_search",
    "pdf_read",
]);

export interface RuntimeStoreScope {
    workspaceId: string;
    sessionId: string;
}

export interface RuntimePointerStore {
    store(
        content: string,
        scope: RuntimeStoreScope,
        signal: AbortSignal,
    ): Promise<{ pointerUri: string; byteSize: number }>;
}

export interface TransformerOptions {
    thresholdBytes?: number;
    boundedReadMaxBytes?: number;
}

function abortError(signal: AbortSignal): Error {
    return signal.reason instanceof Error ? signal.reason : new Error("runtime pointer storage aborted");
}

function abortable<T>(work: Promise<T>, signal: AbortSignal): Promise<T> {
    if (signal.aborted) return Promise.reject(abortError(signal));
    return new Promise<T>((resolve, reject) => {
        const onAbort = (): void => reject(abortError(signal));
        signal.addEventListener("abort", onAbort, { once: true });
        work.then(
            (value) => {
                signal.removeEventListener("abort", onAbort);
                resolve(value);
            },
            (error: unknown) => {
                signal.removeEventListener("abort", onAbort);
                reject(error instanceof Error ? error : new Error("runtime pointer storage failed"));
            },
        );
    });
}

function isBoundedRead(toolName: string): boolean {
    return BOUNDED_READ_TOOLS.has(toolName.replace(/[.-]/g, "_"));
}

export function createLoopbackRuntimeStore(
    options: Pick<RuntimePointerHookOptions, "baseUrl" | "internalToken" | "api">,
): RuntimePointerStore {
    return {
        async store(content, scope) {
            const hookOptions: RuntimePointerHookOptions = {
                workspaceId: scope.workspaceId,
                sessionId: scope.sessionId,
                thresholdBytes: 1,
                ...(options.api !== undefined ? { api: options.api } : {}),
                ...(options.baseUrl !== undefined ? { baseUrl: options.baseUrl } : {}),
                ...(options.internalToken !== undefined ? { internalToken: options.internalToken } : {}),
            };
            const stored = await storeRuntimePointer({ content }, hookOptions);
            if (!stored.stored) throw new Error("runtime pointer was not stored");
            return { pointerUri: stored.pointerUri, byteSize: stored.byteSize };
        },
    };
}

export function createRuntimeToolResultTransformer(
    store: RuntimePointerStore,
    options: TransformerOptions = {},
): ToolResultTransformer {
    const threshold = options.thresholdBytes ?? DEFAULT_THRESHOLD_BYTES;
    const boundedMax = options.boundedReadMaxBytes ?? BOUNDED_READ_MAX_BYTES;
    if (!Number.isSafeInteger(threshold) || threshold < 1 || threshold > MAX_THRESHOLD_BYTES) {
        throw new Error("invalid runtime pointer threshold");
    }
    return {
        async transform(input: ToolResultInput, signal: AbortSignal): Promise<ToolResultOutput> {
            if (signal.aborted) throw abortError(signal);
            if (!input.output.isWellFormed()) throw new Error("tool output is not well-formed text");
            const bytes = Buffer.byteLength(input.output, "utf8");
            if (isBoundedRead(input.toolName)) {
                if (bytes > boundedMax) throw new Error("bounded read result exceeds its own cap");
                return { kind: "inline", text: input.output };
            }
            if (bytes < threshold) return { kind: "inline", text: input.output };
            const scope = { workspaceId: input.workspaceId, sessionId: input.sessionId };
            const stored = await abortable(store.store(input.output, scope, signal), signal);
            const prefix = `securecode://runtime/${scope.workspaceId}/${scope.sessionId}/`;
            if (stored.byteSize !== bytes || !stored.pointerUri.startsWith(prefix)) {
                throw new Error("runtime pointer scope or byte count mismatch");
            }
            return {
                kind: "pointer",
                pointer: stored.pointerUri,
                byteSize: stored.byteSize,
                text: describeStoredOutput({
                    toolName: input.toolName,
                    pointer: stored.pointerUri,
                    byteSize: stored.byteSize,
                    output: input.output,
                    executorLimited: input.preLimitedByExecutor,
                }),
            };
        },
    };
}
