/**
 * HTTP implementation of ContextServiceClient over authenticated loopback.
 * Every response is validated against the contract schema before use.
 * Symbol and pointer operations report NOT_IMPLEMENTED until their owners
 * (3.6 for symbols: the Python R0SymbolService exists since 3.4; 4.3-4.6 for pointers)
 * add the service routes; they never return fake data.
 */
import {
    SCHEMA_REFS,
    type ContractValidator,
    type ErrorResponse,
    type ServiceHealthResponse,
    type TokenCountRequest,
    type TokenCountResult,
} from "@securecode/contracts";
import { ContextServiceError } from "./contextServiceError.js";
import { requestLoopbackJson } from "./loopbackHttp.js";
import type { ContextServiceClient, PointerService, SymbolService, TokenCounter } from "./ports.js";

export interface HttpContextServiceClientOptions {
    baseUrl: string;
    internalToken: string;
    validator: ContractValidator;
    timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 15000;

function pendingOperation(operation: string, ownerTask: string): () => Promise<never> {
    return () =>
        Promise.reject(
            new ContextServiceError("NOT_IMPLEMENTED", `${operation} is not implemented yet`, false, {
                owner_task: ownerTask,
            }),
        );
}

export class HttpContextServiceClient implements ContextServiceClient {
    readonly tokens: TokenCounter;
    readonly symbols: SymbolService;
    readonly pointers: PointerService;
    private readonly options: HttpContextServiceClientOptions;

    constructor(options: HttpContextServiceClientOptions) {
        this.options = options;
        this.tokens = { count: (text, signal) => this.countTokens(text, signal) };
        this.symbols = {
            search: pendingOperation("symbols.search", "3.6"),
            readBundle: pendingOperation("symbols.read_bundle", "3.6"),
        };
        this.pointers = {
            stat: pendingOperation("pointers.stat", "4.3"),
            list: pendingOperation("pointers.list", "4.3"),
            read: pendingOperation("pointers.read", "4.3"),
            search: pendingOperation("pointers.search", "4.6"),
            remove: pendingOperation("pointers.delete", "4.3"),
        };
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
