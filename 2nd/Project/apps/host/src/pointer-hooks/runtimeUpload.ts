/**
 * Streaming upload of one tool output to /internal/v1/runtime/stream. Chunks go out as they are
 * produced (chunked transfer, write() waits for socket drain), so a large command output is never
 * assembled in host memory. abort() destroys the request; the service then discards the partial object.
 */
import { request as httpRequest, type ClientRequest, type IncomingMessage } from "node:http";
import type { ContractValidator, ErrorResponse } from "@securecode/contracts";
import { SCHEMA_REFS } from "@securecode/contracts";
import type { RuntimeOutputMeta, RuntimeScope, RuntimeUpload, StoredRuntimeOutput } from "../cline/adapter/ports.js";
import { ContextServiceError } from "../context-client/contextServiceError.js";
import { loopbackOrigin } from "../context-client/loopbackHttp.js";
import { runtimePrefix, storedFrom } from "./runtimeResponses.js";

const STREAM_PATH = "/internal/v1/runtime/stream";
const RESPONSE_LIMIT_BYTES = 256 * 1024;
const HEADER_VALUE = /^[A-Za-z0-9_./+-]{1,128}$/;
/** Contract RunId (contracts/common/primitives.schema.json). */
const RUN_ID = /^run_[A-Za-z0-9-]{8,64}$/;

export interface UploadOptions {
    baseUrl: string;
    internalToken: string;
    validator: ContractValidator;
    scope: RuntimeScope;
    meta: RuntimeOutputMeta;
    signal: AbortSignal;
}

function transportError(reason: string): ContextServiceError {
    return new ContextServiceError("SERVICE_UNAVAILABLE", "runtime stream upload failed", true, { reason });
}

function readResponse(response: IncomingMessage): Promise<{ status: number; body: unknown }> {
    return new Promise((resolve, reject) => {
        const chunks: Buffer[] = [];
        let size = 0;
        response.on("data", (chunk: Buffer) => {
            size += chunk.length;
            if (size > RESPONSE_LIMIT_BYTES) {
                response.destroy();
                reject(transportError("response_too_large"));
                return;
            }
            chunks.push(chunk);
        });
        response.once("error", () => reject(transportError("response_error")));
        response.once("end", () => {
            try {
                const text = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks));
                resolve({ status: response.statusCode ?? 0, body: JSON.parse(text) as unknown });
            } catch {
                reject(transportError("invalid_response"));
            }
        });
    });
}

export function openRuntimeUpload(options: UploadOptions): RuntimeUpload {
    const { scope, meta, validator } = options;
    runtimePrefix(scope);
    if (meta.runId !== undefined && !RUN_ID.test(meta.runId))
        throw new ContextServiceError("VALIDATION_FAILED", "invalid upload run id", false);
    for (const value of [meta.origin, meta.mediaType]) {
        if (!HEADER_VALUE.test(value))
            throw new ContextServiceError("VALIDATION_FAILED", "invalid upload metadata", false);
    }
    const origin = new URL(loopbackOrigin(options.baseUrl, STREAM_PATH, options.internalToken));
    let failure: Error | null = null;
    const request: ClientRequest = httpRequest({
        host: origin.hostname.replace(/^\[|\]$/g, ""),
        port: origin.port,
        path: STREAM_PATH,
        method: "POST",
        signal: options.signal,
        headers: {
            authorization: `Bearer ${options.internalToken}`,
            "content-type": "application/octet-stream",
            "transfer-encoding": "chunked",
            "x-securecode-workspace-id": scope.workspaceId,
            "x-securecode-session-id": scope.sessionId,
            "x-securecode-origin": meta.origin,
            "x-securecode-media-type": meta.mediaType,
            "x-securecode-truncated": meta.truncatedBeforeStorage ? "true" : "false",
            ...(meta.runId ? { "x-securecode-run-id": meta.runId } : {}),
        },
    });
    // Remember the first transport failure (abort signal, reset) for every later call.
    request.on("error", () => {
        failure ??= transportError(options.signal.aborted ? "aborted" : "transport");
    });
    const response = new Promise<{ status: number; body: unknown }>((resolve, reject) => {
        request.once("response", (incoming) => {
            readResponse(incoming).then(resolve, reject);
        });
        request.once("error", () => reject(failure ?? transportError("transport")));
    });
    // Keep the rejection observed; finish() reports it.
    response.catch(() => undefined);
    let bytes = 0;

    return {
        write(chunk) {
            if (failure || request.destroyed) return Promise.reject(failure ?? transportError("transport"));
            bytes += chunk.length;
            // The write callback runs once the chunk is handed to the socket, or with an error if the
            // request was destroyed meanwhile; waiting for it is the backpressure and never hangs.
            return new Promise<void>((resolve, reject) => {
                request.write(chunk, (error) => {
                    if (error) reject(failure ?? transportError("transport"));
                    else resolve();
                });
            });
        },
        async finish(): Promise<StoredRuntimeOutput> {
            if (failure) throw failure;
            request.end();
            const result = await response;
            if (result.status >= 200 && result.status < 300) return storedFrom(result.body, scope, validator, bytes);
            if (!validator.validate(SCHEMA_REFS.errorResponse, result.body).valid) {
                throw transportError(`http_${result.status}`);
            }
            throw ContextServiceError.fromApiError((result.body as ErrorResponse).error);
        },
        abort() {
            failure ??= transportError("aborted");
            request.destroy(failure);
        },
    };
}
