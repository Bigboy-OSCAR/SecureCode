/**
 * HTTP implementation of ContextServiceClient over authenticated loopback.
 * Every response is validated against the contract schema before use.
 * The capability clients (R0, workspaces, Source, Runtime admin, PDF) share these options.
 */
import {
    SCHEMA_REFS,
    type ContextSelectRequest,
    type ContextSelectResponse,
    type ContractValidator,
    type ErrorResponse,
    type RequestTokenCountRequest,
    type ServiceHealthResponse,
    type TokenCountRequest,
    type TokenCountResult,
} from "@securecode/contracts";
import { ContextServiceError } from "./contextServiceError.js";
import { requestLoopbackJson } from "./loopbackHttp.js";
import { createPdfClient, type PdfService } from "./pdfClient.js";
import type { ContextSelector, ContextServiceClient, TokenCounter } from "./ports.js";
import {
    createRuntimeAdminService,
    createSourceService,
    createSymbolService,
    createWorkspaceService,
    type RuntimeAdminService,
    type SourceService,
    type SymbolService,
    type WorkspaceService,
} from "./workspaceServices.js";

export interface HttpContextServiceClientOptions {
    baseUrl: string;
    internalToken: string;
    validator: ContractValidator;
    timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 15000;

export class HttpContextServiceClient implements ContextServiceClient {
    readonly tokens: TokenCounter;
    readonly context: ContextSelector;
    readonly symbols: SymbolService;
    readonly workspaces: WorkspaceService;
    readonly sources: SourceService;
    readonly runtime: RuntimeAdminService;
    readonly pdf: PdfService;
    private readonly options: HttpContextServiceClientOptions;

    constructor(options: HttpContextServiceClientOptions) {
        this.options = options;
        this.tokens = {
            count: (text, signal) => this.countTokens(text, signal),
            countRequest: (request, signal) => this.countRequest(request, signal),
        };
        this.context = { select: (request, signal) => this.selectContext(request, signal) };
        this.symbols = createSymbolService(options);
        this.workspaces = createWorkspaceService(options);
        this.sources = createSourceService(options);
        this.runtime = createRuntimeAdminService(options);
        this.pdf = createPdfClient(options);
    }

    async health(signal?: AbortSignal): Promise<ServiceHealthResponse> {
        const body = await this.request("/internal/v1/health", undefined, signal);
        return this.options.validator.parse<ServiceHealthResponse>(SCHEMA_REFS.serviceHealthResponse, body);
    }

    private async countTokens(text: string, signal?: AbortSignal): Promise<TokenCountResult> {
        // Lone surrogates would silently become U+FFFD in UTF-8; reject them like the service does.
        if (!text.isWellFormed()) {
            throw new ContextServiceError("VALIDATION_FAILED", "text contains invalid Unicode", false, {
                reason: "invalid_unicode",
            });
        }
        const byteSize = Buffer.byteLength(text, "utf8");
        if (byteSize === 0) {
            throw new ContextServiceError("VALIDATION_FAILED", "text must not be empty", false, { reason: "empty" });
        }
        if (byteSize > 1024 * 1024) {
            throw new ContextServiceError("PAYLOAD_TOO_LARGE", "token count input too large", false, {
                text_bytes: byteSize,
            });
        }
        const request: TokenCountRequest = { schema_version: "1", text };
        const body = await this.request("/internal/v1/tokens/count", request, signal);
        const count = this.options.validator.parse<TokenCountResult>(SCHEMA_REFS.tokenCountResult, body);
        if (count.text_bytes !== byteSize) {
            throw new ContextServiceError("SERVICE_UNAVAILABLE", "token result input size mismatch", true);
        }
        return count;
    }

    private async countRequest(request: RequestTokenCountRequest, signal?: AbortSignal): Promise<TokenCountResult> {
        const body = await this.request("/internal/v1/tokens/request", request, signal);
        const count = this.options.validator.parse<TokenCountResult>(SCHEMA_REFS.tokenCountResult, body);
        if (count.framing !== "provider_request") {
            throw new ContextServiceError("SERVICE_UNAVAILABLE", "request count used an unexpected framing", true);
        }
        return count;
    }

    private async selectContext(request: ContextSelectRequest, signal?: AbortSignal): Promise<ContextSelectResponse> {
        this.options.validator.parse<ContextSelectRequest>(SCHEMA_REFS.contextSelectRequest, request);
        const body = await this.request("/internal/v1/context/select", request, signal);
        return this.options.validator.parse<ContextSelectResponse>(SCHEMA_REFS.contextSelectResponse, body);
    }

    private async request(path: string, payload: unknown, signal?: AbortSignal): Promise<unknown> {
        const timeoutSignal = AbortSignal.timeout(this.options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
        const response = await requestLoopbackJson(
            this.options.baseUrl,
            path,
            this.options.internalToken,
            payload,
            signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal,
        );
        const body = response.body;
        if (response.ok) {
            return body;
        }
        const validated = this.options.validator.validate(SCHEMA_REFS.errorResponse, body);
        if (!validated.valid) {
            throw new ContextServiceError("SERVICE_UNAVAILABLE", "context-service returned an invalid error", true, {
                http_status: response.status,
            });
        }
        throw ContextServiceError.fromApiError((body as ErrorResponse).error);
    }
}
