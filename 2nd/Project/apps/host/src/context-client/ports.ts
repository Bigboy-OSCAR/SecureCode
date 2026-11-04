/**
 * App-internal ports between the host and the Python context-service.
 * Shapes come from @securecode/contracts (generated from JSON Schema).
 * Pointer DTOs are owned by 4.2 (contracts/pointers); until those schemas land,
 * PointerService only fixes the operation names and opaque boundary types.
 */
import type {
    PointerUri,
    ServiceHealthResponse,
    SymbolBundle,
    SymbolBundleRequest,
    SymbolSearchRequest,
    SymbolSearchResponse,
    TokenCountResult,
} from "@securecode/contracts";

/** tokens.count: body token count of one text (provider_estimate for the 3.1 model, never chars/4). */
export interface TokenCounter {
    count(text: string, signal?: AbortSignal): Promise<TokenCountResult>;
}

/** symbols.search / symbols.read_bundle (3.3/3.4). R0 TF-IDF only: no LLM selection or embeddings. */
export interface SymbolService {
    search(request: SymbolSearchRequest, signal?: AbortSignal): Promise<SymbolSearchResponse>;
    readBundle(request: SymbolBundleRequest, signal?: AbortSignal): Promise<SymbolBundle>;
}

/**
 * Boundary type for 4.2-owned pointer payloads. Replace with the generated
 * PointerDescriptor / ReadRequest / ReadResult types when contracts/pointers exists.
 */
export type PointerContractPayload = Readonly<Record<string, unknown>>;

/** runtime.* and source.* operations exposed to the host (4.3-4.6). Admin operations stay internal. */
export interface PointerService {
    stat(pointer: PointerUri, signal?: AbortSignal): Promise<PointerContractPayload>;
    list(request: PointerContractPayload, signal?: AbortSignal): Promise<PointerContractPayload>;
    read(request: PointerContractPayload, signal?: AbortSignal): Promise<PointerContractPayload>;
    search(request: PointerContractPayload, signal?: AbortSignal): Promise<PointerContractPayload>;
    remove(request: PointerContractPayload, signal?: AbortSignal): Promise<PointerContractPayload>;
}

/** One authenticated loopback client for every context-service capability. */
export interface ContextServiceClient {
    health(signal?: AbortSignal): Promise<ServiceHealthResponse>;
    readonly tokens: TokenCounter;
    readonly symbols: SymbolService;
    readonly pointers: PointerService;
}
