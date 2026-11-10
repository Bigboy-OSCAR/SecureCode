/**
 * App-internal ports between the host and the Python context-service.
 * Shapes come from @securecode/contracts (generated from JSON Schema).
 * 3.6 connects every capability: tokens, context.select, R0, workspace roots/index, Source, Runtime
 * admin and PDF.
 */
import type { PdfService } from "./pdfClient.js";
import type { RuntimeAdminService, SourceService, SymbolService, WorkspaceService } from "./workspaceServices.js";
import type {
    ContextSelectRequest,
    ContextSelectResponse,
    RequestTokenCountRequest,
    ServiceHealthResponse,
    TokenCountResult,
} from "@securecode/contracts";

/** tokens.count: body token count of one text (provider_estimate for the 3.1 model, never chars/4). */
export interface TokenCounter {
    count(text: string, signal?: AbortSignal): Promise<TokenCountResult>;
    /** tokens.request (4.8): input tokens of one serialized provider request, framing as sent. */
    countRequest(request: RequestTokenCountRequest, signal?: AbortSignal): Promise<TokenCountResult>;
}

/** context.select (4.8): deterministic plan from explicit, current-task and R0 candidates. */
export interface ContextSelector {
    select(request: ContextSelectRequest, signal?: AbortSignal): Promise<ContextSelectResponse>;
}

export type { RuntimeAdminService, SourceService, SymbolService, WorkspaceService } from "./workspaceServices.js";

/** One authenticated loopback client for every context-service capability. */
export interface ContextServiceClient {
    health(signal?: AbortSignal): Promise<ServiceHealthResponse>;
    readonly tokens: TokenCounter;
    readonly context: ContextSelector;
    readonly symbols: SymbolService;
    readonly workspaces: WorkspaceService;
    readonly sources: SourceService;
    readonly runtime: RuntimeAdminService;
    readonly pdf: PdfService;
}
