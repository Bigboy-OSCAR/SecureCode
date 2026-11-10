/**
 * SDK-facing ports implemented by other owners and wired by the Cline adapter (3.5/3.6).
 * They are SDK-independent on purpose: the adapter maps @cline/sdk hook
 * contexts (afterTool, ClineCoreOptions.fetch) to these shapes, so pointer and
 * budget code never imports the SDK. Both ports fail closed: they throw
 * instead of passing raw content through (3.1 S-03/S-04/S-05).
 */
import type {
    CountMode,
    ErrorCode,
    PointerReadRequest,
    PointerReadResult,
    PointerSearchRequest,
    PointerSearchResult,
    PointerUri,
} from "@securecode/contracts";

/** Workspace and session that own Runtime Pointers. */
export interface RuntimeScope {
    workspaceId: string;
    sessionId: string;
}

/** What produced an output and whether bytes were dropped before it reached storage. */
export interface RuntimeOutputMeta {
    origin: string;
    mediaType: string;
    truncatedBeforeStorage: boolean;
}

export interface StoredRuntimeOutput {
    pointer: PointerUri;
    byteSize: number;
}

/** Streaming upload: write() resolves when the chunk was accepted (backpressure); abort() discards everything. */
export interface RuntimeUpload {
    write(chunk: Uint8Array): Promise<void>;
    finish(): Promise<StoredRuntimeOutput>;
    abort(): void;
}

/**
 * 4.3 Runtime store as seen by the host (context-service /internal/v1/runtime/*).
 * Every call is scoped; failures throw ContextServiceError and never return raw content.
 */
export interface RuntimePointerService {
    store(
        scope: RuntimeScope,
        content: string,
        meta: RuntimeOutputMeta,
        signal: AbortSignal,
    ): Promise<StoredRuntimeOutput>;
    openUpload(scope: RuntimeScope, meta: RuntimeOutputMeta, signal: AbortSignal): RuntimeUpload;
    read(
        scope: RuntimeScope,
        request: Omit<PointerReadRequest, "schema_version">,
        signal: AbortSignal,
    ): Promise<PointerReadResult>;
    search(
        scope: RuntimeScope,
        request: Omit<PointerSearchRequest, "schema_version">,
        signal: AbortSignal,
    ): Promise<PointerSearchResult>;
    /** Cheap authenticated call proving the store is reachable for this scope. */
    probe(scope: RuntimeScope, signal: AbortSignal): Promise<void>;
    clearSession(scope: RuntimeScope, signal: AbortSignal): Promise<number>;
}

/** Output the project executor already streamed into the store before afterTool ran. */
export interface ExecutorCapture {
    pointer: PointerUri;
    byteSize: number;
    /** Bytes the command produced; larger than byteSize when the capture cap cut it. */
    producedBytes: number;
    truncated: boolean;
}

/** Input of afterTool after the adapter extracts the local tool result. */
export interface ToolResultInput {
    workspaceId: string;
    sessionId: string;
    runId: string;
    toolCallId: string;
    toolName: string;
    /** Full local output as received by afterTool (SDK truncation happens later, 3.1 C-07). */
    output: string;
    outputBytes: number;
    /** true when a project executor already stored/limited the output before the hook. */
    preLimitedByExecutor: boolean;
    /** The tool reported an error; kept in the descriptor when the output is replaced. */
    isError?: boolean;
    /** Set when the executor streamed the output itself; the transformer must not store it again. */
    executorStored?: ExecutorCapture;
}

export type ToolResultOutput =
    { kind: "inline"; text: string } | { kind: "pointer"; text: string; pointer: PointerUri; byteSize: number };

/**
 * 4.4 (임우형) implements; the adapter returns `{ result }` from afterTool with `text`.
 * Must throw on store failure or timeout; never return the raw output as fallback.
 */
export interface ToolResultTransformer {
    transform(input: ToolResultInput, signal: AbortSignal): Promise<ToolResultOutput>;
    /** Throws unless storage for this scope is reachable; the adapter calls it before each SDK turn. */
    ready?(scope: RuntimeScope, signal: AbortSignal): Promise<void>;
}

/** Final serialized provider request seen by the fetch gate (after SDK framing). */
export interface OutboundModelRequest {
    providerId: string;
    modelId: string;
    /** Exact JSON body that would leave the process. */
    body: string;
    maxOutputTokens: number;
}

export type ModelRequestDecision =
    | { allow: true; countedTokens: number; countMode: CountMode }
    | { allow: false; code: Extract<ErrorCode, "BUDGET_EXCEEDED" | "TOKENIZER_UNAVAILABLE">; message: string };

/**
 * 4.8 (임우형) implements the total request gate; 3.2 only provides body
 * counting through TokenCounter. Wired into ClineCoreOptions.fetch by 3.5.
 */
export interface ModelRequestGate {
    check(request: OutboundModelRequest, signal: AbortSignal): Promise<ModelRequestDecision>;
}
