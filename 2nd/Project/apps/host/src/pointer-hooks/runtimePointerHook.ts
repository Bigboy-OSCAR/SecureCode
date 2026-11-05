/** Legacy Runtime Pointer transport. Use the authenticated loopback API with an explicit session scope. */
import { requestLoopbackJson } from "../context-client/loopbackHttp.js";

export interface RuntimePointerHookOptions {
    baseUrl?: string;
    internalToken?: string;
    workspaceId: string;
    sessionId: string;
    thresholdBytes?: number;
}

export type RuntimePointerResult =
    { stored: false } | { stored: true; pointerUri: string; pointerId: string; byteSize: number };

const SEGMENT = /^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}$/;
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const MAX_READ_BYTES = 16 * 1024;
const MAX_STORE_BYTES = 32 * 1024 * 1024;

function endpoint(options: RuntimePointerHookOptions): string {
    for (const segment of [options.workspaceId, options.sessionId]) {
        if (!SEGMENT.test(segment)) {
            throw new Error("invalid runtime pointer scope");
        }
    }
    return options.baseUrl ?? "http://127.0.0.1:8000";
}

async function requestPointer(
    options: RuntimePointerHookOptions,
    path: string,
    data: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const result = await requestLoopbackJson(
        endpoint(options),
        path,
        options.internalToken ?? process.env.SECURECODE_INTERNAL_TOKEN ?? "",
        { workspace_id: options.workspaceId, session_id: options.sessionId, ...data },
        AbortSignal.timeout(5000),
    );
    if (!result.ok || result.body === null || typeof result.body !== "object" || Array.isArray(result.body)) {
        throw new Error("runtime pointer service request failed");
    }
    return result.body as Record<string, unknown>;
}

export async function storeRuntimePointer(
    toolResult: { toolName?: string; content: string },
    options: RuntimePointerHookOptions,
): Promise<RuntimePointerResult> {
    const threshold = options.thresholdBytes ?? 4096;
    if (
        !Number.isSafeInteger(threshold) ||
        threshold < 1 ||
        threshold > MAX_STORE_BYTES ||
        !toolResult.content.isWellFormed()
    ) {
        throw new Error("invalid runtime pointer input");
    }
    const byteSize = Buffer.byteLength(toolResult.content, "utf8");
    if (byteSize > MAX_STORE_BYTES) throw new Error("tool output exceeds runtime store limit");
    if (byteSize < threshold) return { stored: false };
    if (!/^ws_[A-Za-z0-9-]{8,64}$/.test(options.workspaceId) || !/^ses_[A-Za-z0-9-]{8,64}$/.test(options.sessionId)) {
        throw new Error("invalid runtime pointer creation scope");
    }
    const record = await requestPointer(options, "/api/v1/pointers/runtime", { content: toolResult.content });
    const id = record.pointer_id;
    if (typeof id !== "string" || !UUID.test(id)) throw new Error("invalid runtime pointer response");
    const pointerUri = `securecode://runtime/${options.workspaceId}/${options.sessionId}/${id}?v=1`;
    if (record.pointer_uri !== pointerUri || record.byte_size !== byteSize) {
        throw new Error("runtime pointer scope or byte count mismatch");
    }
    return { stored: true, pointerId: id, pointerUri, byteSize };
}

/** Read only a caller-selected slice of a pointer owned by this session. Never auto-inject it before a model call. */
export async function readRuntimePointer(
    pointerUri: string,
    options: RuntimePointerHookOptions,
    cursor = 0,
    maxBytes = MAX_READ_BYTES,
): Promise<{ content: string; nextCursor: number | null; truncated: boolean; byteSize: number }> {
    const prefix = `securecode://runtime/${options.workspaceId}/${options.sessionId}/`;
    const suffix = pointerUri.slice(prefix.length);
    const id = suffix.endsWith("?v=1") ? suffix.slice(0, -4) : suffix;
    if (
        !pointerUri.startsWith(prefix) ||
        !UUID.test(id) ||
        !Number.isSafeInteger(cursor) ||
        cursor < 0 ||
        !Number.isSafeInteger(maxBytes) ||
        maxBytes < 1 ||
        maxBytes > MAX_READ_BYTES
    ) {
        throw new Error("invalid runtime pointer read range or scope");
    }
    const record = await requestPointer(options, "/api/v1/pointers/runtime/read", {
        pointer_id: id,
        cursor,
        max_bytes: maxBytes,
    });
    const { content, byte_size: byteSize, truncated, next_cursor: nextCursor } = record;
    if (
        typeof content !== "string" ||
        !content.isWellFormed() ||
        typeof byteSize !== "number" ||
        !Number.isSafeInteger(byteSize) ||
        typeof truncated !== "boolean"
    )
        throw new Error("invalid runtime pointer read response");
    const bytes = Buffer.byteLength(content);
    const end = cursor + bytes;
    if (
        bytes > maxBytes ||
        end > byteSize ||
        truncated !== end < byteSize ||
        nextCursor !== (truncated ? end : null) ||
        (truncated && bytes === 0)
    ) {
        throw new Error("invalid runtime pointer read boundaries");
    }
    return { content, nextCursor: truncated ? end : null, truncated, byteSize };
}
