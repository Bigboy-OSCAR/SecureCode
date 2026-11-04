/**
 * HTTP implementation of ContextServiceClient over authenticated loopback.
 * Every response is validated against the contract schema before use.
 * Symbol and pointer operations report NOT_IMPLEMENTED until their owners
 * (3.3/3.4, 4.3-4.6) add the service routes; they never return fake data.
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
            search: pendingOperation("symbols.search", "3.4"),
            readBundle: pendingOperation("symbols.read_bundle", "3.4"),
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
        const body = await this.request("GET", "/internal/v1/health", undefined, signal);
        return this.options.validator.parse<ServiceHealthResponse>(SCHEMA_REFS.serviceHealthResponse, body);
    }

    private async countTokens(text: string, signal?: AbortSignal): Promise<TokenCountResult> {
        // Lone surrogates would silently become U+FFFD in UTF-8; reject them like the service does.
        if (!text.isWellFormed()) {
            throw new ContextServiceError("VALIDATION_FAILED", "text contains invalid Unicode", false, {
                reason: "invalid_unicode",
            });
        }
        const request: TokenCountRequest = { schema_version: "1", text };
        const body = await this.request("POST", "/internal/v1/tokens/count", request, signal);
        return this.options.validator.parse<TokenCountResult>(SCHEMA_REFS.tokenCountResult, body);
    }

    private async request(method: string, path: string, payload: unknown, signal?: AbortSignal): Promise<unknown> {
        const timeoutSignal = AbortSignal.timeout(this.options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
        let response: Response;
        try {
            response = await fetch(`${this.options.baseUrl}${path}`, {
                method,
                headers: {
                    authorization: `Bearer ${this.options.internalToken}`,
                    ...(payload === undefined ? {} : { "content-type": "application/json" }),
                },
                body: payload === undefined ? null : JSON.stringify(payload),
                signal: signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal,
            });
        } catch (error) {
            const reason = error instanceof Error && error.name === "TimeoutError" ? "timeout" : "unreachable";
            throw new ContextServiceError("SERVICE_UNAVAILABLE", "context-service is not reachable", true, {
                reason,
            });
        }

        const body: unknown = await response.json().catch(() => undefined);
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
