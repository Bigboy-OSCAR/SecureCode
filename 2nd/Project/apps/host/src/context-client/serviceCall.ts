/**
 * One authenticated loopback call to the context-service: JSON body, timeout combined with the caller's
 * signal, contract-validated error envelope mapped to ContextServiceError. Success bodies are returned
 * as unknown; each caller validates them against its own contract schema.
 */
import { SCHEMA_REFS, type ContractValidator, type ErrorResponse } from "@securecode/contracts";
import { ContextServiceError } from "./contextServiceError.js";
import { requestLoopbackJson } from "./loopbackHttp.js";

export interface ServiceCallOptions {
    baseUrl: string;
    internalToken: string;
    validator: ContractValidator;
    timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 15000;

export async function callService(
    options: ServiceCallOptions,
    path: string,
    payload: unknown,
    signal?: AbortSignal,
): Promise<unknown> {
    const timeout = AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
    const response = await requestLoopbackJson(
        options.baseUrl,
        path,
        options.internalToken,
        payload,
        signal ? AbortSignal.any([signal, timeout]) : timeout,
    );
    if (response.ok) return response.body;
    if (!options.validator.validate(SCHEMA_REFS.errorResponse, response.body).valid) {
        throw new ContextServiceError("SERVICE_UNAVAILABLE", "context-service returned an invalid error", true, {
            http_status: response.status,
        });
    }
    throw ContextServiceError.fromApiError((response.body as ErrorResponse).error);
}

/** Validates a success body against a schema ref; a mismatch is a service fault, never data. */
export function parseAs<T>(options: ServiceCallOptions, schemaRef: string, body: unknown): T {
    const result = options.validator.validate(schemaRef, body);
    if (!result.valid) {
        throw new ContextServiceError("SERVICE_UNAVAILABLE", "context-service returned an invalid result", true, {
            schema: schemaRef.split("#/definitions/")[1] ?? schemaRef,
        });
    }
    return body as T;
}
