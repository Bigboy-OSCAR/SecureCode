/**
 * Host client for the 4.3 Runtime store (context-service /internal/v1/runtime/*). Every response is
 * validated against the contracts and checked against the caller's scope; any mismatch or error
 * envelope becomes a ContextServiceError, so callers never fall back to raw tool output.
 */
import {
    SCHEMA_REFS,
    type ContractValidator,
    type ErrorResponse,
    type PointerListResult,
    type PointerReadResult,
    type PointerSearchResult,
} from "@securecode/contracts";
import type { RuntimeOutputMeta, RuntimePointerService, RuntimeScope } from "../cline/adapter/ports.js";
import { ContextServiceError } from "../context-client/contextServiceError.js";
import { requestLoopbackJson } from "../context-client/loopbackHttp.js";
import { invalidResponse, runtimePrefix, storedFrom } from "./runtimeResponses.js";
import { openRuntimeUpload } from "./runtimeUpload.js";

export interface RuntimeClientOptions {
    baseUrl: string;
    internalToken: string;
    validator: ContractValidator;
    timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 10000;
export function createRuntimeClient(options: RuntimeClientOptions): RuntimePointerService {
    const { validator } = options;

    async function call(path: string, scope: RuntimeScope, payload: object, signal: AbortSignal): Promise<unknown> {
        runtimePrefix(scope);
        const timeout = AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
        const response = await requestLoopbackJson(
            options.baseUrl,
            path,
            options.internalToken,
            { workspace_id: scope.workspaceId, session_id: scope.sessionId, ...payload },
            AbortSignal.any([signal, timeout]),
        );
        if (response.ok) return response.body;
        if (!validator.validate(SCHEMA_REFS.errorResponse, response.body).valid) {
            throw invalidResponse(`http_${response.status}`);
        }
        throw ContextServiceError.fromApiError((response.body as ErrorResponse).error);
    }

    function checkPointer(scope: RuntimeScope, pointer: string, returned: string): void {
        if (!pointer.startsWith(runtimePrefix(scope)) || returned !== pointer)
            throw invalidResponse("pointer_mismatch");
    }

    return {
        async store(scope, content, meta: RuntimeOutputMeta, signal) {
            if (!content.isWellFormed())
                throw new ContextServiceError("VALIDATION_FAILED", "output is not text", false);
            const body = await call(
                "/internal/v1/runtime/pointers",
                scope,
                {
                    content,
                    media_type: meta.mediaType,
                    origin: meta.origin,
                    truncated_before_storage: meta.truncatedBeforeStorage,
                },
                signal,
            );
            return storedFrom(body, scope, validator, Buffer.byteLength(content, "utf8"));
        },
        openUpload(scope, meta, signal) {
            return openRuntimeUpload({ ...options, scope, meta, signal });
        },
        async read(scope, request, signal) {
            const body = await call("/internal/v1/runtime/read", scope, { schema_version: "1", ...request }, signal);
            const result = validator.parse<PointerReadResult>(SCHEMA_REFS.pointerReadResult, body);
            checkPointer(scope, request.pointer, result.pointer);
            return result;
        },
        async search(scope, request, signal) {
            const body = await call("/internal/v1/runtime/search", scope, { schema_version: "1", ...request }, signal);
            const result = validator.parse<PointerSearchResult>(SCHEMA_REFS.pointerSearchResult, body);
            checkPointer(scope, request.pointer, result.pointer);
            return result;
        },
        async probe(scope, signal) {
            const body = await call("/internal/v1/runtime/list", scope, { kind: "runtime", limit: 1 }, signal);
            validator.parse<PointerListResult>(SCHEMA_REFS.pointerListResult, body);
        },
        async clearSession(scope, signal) {
            const body = (await call("/internal/v1/runtime/sessions/clear", scope, {}, signal)) as {
                deleted?: unknown;
            };
            if (typeof body.deleted !== "number") throw invalidResponse("clear_result");
            return body.deleted;
        },
    };
}
