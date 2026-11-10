/**
 * 4.4 ToolResultTransformer: replaces large tool output with a Runtime Pointer descriptor before
 * it reaches the model or SDK history. Policies:
 *  - bounded read tools (runtime/source/pdf reads) stay inline within their own cap and are never
 *    stored again (no pointer-in-pointer);
 *  - outputs the command executor already streamed into the store pass through as that pointer;
 *  - other outputs below the threshold stay inline; larger ones are stored with origin, media type
 *    and JSON status facts kept in the descriptor.
 * Every failure, timeout or abort throws; raw output is never returned as a fallback.
 */
import type {
    RuntimePointerService,
    ToolResultInput,
    ToolResultOutput,
    ToolResultTransformer,
} from "../cline/adapter/ports.js";
import { runtimePrefix } from "./runtimeResponses.js";
import { describeStoredOutput, FACT_SCAN_LIMIT_BYTES, factsOf, statusLineOf } from "./runtimeDescriptor.js";

export const DEFAULT_THRESHOLD_BYTES = 4096;
export const BOUNDED_READ_MAX_BYTES = 32 * 1024;
const EXECUTOR_DESCRIPTOR_MAX_BYTES = 8 * 1024;
const MAX_THRESHOLD_BYTES = 32 * 1024 * 1024;
export const BOUNDED_READ_TOOLS: ReadonlySet<string> = new Set([
    "runtime_read",
    "runtime_search",
    "source_read",
    "source_search",
    "pdf_read_pages",
    // 3.6: Source-backed file reads and R0 bundles are bounded by the service caps (16 KiB).
    "read_file",
    "search_file",
    "code_search",
    "code_read",
    "pdf_search",
]);

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

export function isBoundedRead(toolName: string): boolean {
    return BOUNDED_READ_TOOLS.has(toolName.replace(/[.-]/g, "_"));
}

/** Tool name as a safe origin label for the store. */
function originOf(toolName: string): string {
    const cleaned = toolName.replace(/[^A-Za-z0-9_.-]/g, "_").slice(0, 64);
    return cleaned === "" ? "tool_output" : cleaned;
}

function mediaTypeOf(output: string, bytes: number): string {
    const head = output.trimStart()[0];
    if ((head !== "{" && head !== "[") || bytes > FACT_SCAN_LIMIT_BYTES) return "text/plain";
    try {
        JSON.parse(output);
        return "application/json";
    } catch {
        return "text/plain";
    }
}

export function createRuntimeToolResultTransformer(
    service: RuntimePointerService,
    options: TransformerOptions = {},
): ToolResultTransformer {
    const threshold = options.thresholdBytes ?? DEFAULT_THRESHOLD_BYTES;
    const boundedMax = options.boundedReadMaxBytes ?? BOUNDED_READ_MAX_BYTES;
    if (!Number.isSafeInteger(threshold) || threshold < 1 || threshold > MAX_THRESHOLD_BYTES) {
        throw new Error("invalid runtime pointer threshold");
    }
    return {
        ready: (scope, signal) => service.probe(scope, signal),
        async transform(input: ToolResultInput, signal: AbortSignal): Promise<ToolResultOutput> {
            if (signal.aborted) throw abortError(signal);
            if (!input.output.isWellFormed()) throw new Error("tool output is not well-formed text");
            const scope = { workspaceId: input.workspaceId, sessionId: input.sessionId };
            const bytes = Buffer.byteLength(input.output, "utf8");
            if (isBoundedRead(input.toolName)) {
                if (bytes > boundedMax) throw new Error("bounded read result exceeds its own cap");
                return { kind: "inline", text: input.output };
            }
            if (input.executorStored) {
                const captured = input.executorStored;
                if (!captured.pointer.startsWith(runtimePrefix(scope)) || bytes > EXECUTOR_DESCRIPTOR_MAX_BYTES) {
                    throw new Error("executor capture does not belong to this run");
                }
                return { kind: "pointer", pointer: captured.pointer, byteSize: captured.byteSize, text: input.output };
            }
            if (bytes < threshold) return { kind: "inline", text: input.output };
            const meta = {
                origin: originOf(input.toolName),
                mediaType: mediaTypeOf(input.output, bytes),
                truncatedBeforeStorage: input.preLimitedByExecutor,
            };
            const stored = await abortable(service.store(scope, input.output, meta, signal), signal);
            if (stored.byteSize !== bytes || !stored.pointer.startsWith(runtimePrefix(scope))) {
                throw new Error("runtime pointer scope or byte count mismatch");
            }
            return {
                kind: "pointer",
                pointer: stored.pointer,
                byteSize: stored.byteSize,
                text: describeStoredOutput({
                    toolName: input.toolName,
                    pointer: stored.pointer,
                    byteSize: stored.byteSize,
                    preview: input.output.slice(0, 2048),
                    status: statusLineOf(input.output),
                    facts: factsOf(input.output, bytes),
                    isError: input.isError ?? false,
                    truncation: input.preLimitedByExecutor ? { producedBytes: null } : null,
                }),
            };
        },
    };
}
