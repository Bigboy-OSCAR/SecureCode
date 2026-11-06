/**
 * Reads a JSON request body under a byte cap and validates it against a
 * contract schema. Oversized, non-JSON or invalid bodies never reach handlers.
 */
import type { IncomingMessage } from "node:http";
import type { ContractValidator } from "@securecode/contracts";
import { RouteFailure } from "./routeFailure.js";

export const DEFAULT_BODY_LIMIT_BYTES = 64 * 1024;
/** RunCreateRequest.prompt allows 32,000 characters; JSON escaping can grow that up to six times. */
export const RUN_BODY_LIMIT_BYTES = 256 * 1024;

export async function readJsonBody(request: IncomingMessage, limitBytes = DEFAULT_BODY_LIMIT_BYTES): Promise<unknown> {
    const contentType = (request.headers["content-type"] ?? "").split(";", 1)[0]?.trim().toLowerCase() ?? "";
    if (contentType !== "application/json") {
        throw new RouteFailure("VALIDATION_FAILED", "a JSON request body is required", { reason: "content_type" });
    }
    const declared = Number(request.headers["content-length"] ?? "0");
    if (Number.isFinite(declared) && declared > limitBytes) {
        request.resume();
        throw new RouteFailure("PAYLOAD_TOO_LARGE", "request body is too large", { max_bytes: limitBytes });
    }
    const chunks: Buffer[] = [];
    let size = 0;
    for await (const chunk of request) {
        const buffer = chunk as Buffer;
        size += buffer.length;
        if (size > limitBytes) {
            request.resume();
            throw new RouteFailure("PAYLOAD_TOO_LARGE", "request body is too large", { max_bytes: limitBytes });
        }
        chunks.push(buffer);
    }
    try {
        return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks))) as unknown;
    } catch {
        throw new RouteFailure("VALIDATION_FAILED", "request body is not valid JSON", { reason: "json" });
    }
}

export function validateBody<T>(validator: ContractValidator, schemaRef: string, body: unknown): T {
    const result = validator.validate(schemaRef, body);
    if (!result.valid) {
        throw new RouteFailure("VALIDATION_FAILED", "request does not match the contract", {
            reason: "schema",
            first_error: (result.errors[0] ?? "invalid").slice(0, 200),
        });
    }
    return body as T;
}

export async function readContractBody<T>(
    request: IncomingMessage,
    validator: ContractValidator,
    schemaRef: string,
    limitBytes = DEFAULT_BODY_LIMIT_BYTES,
): Promise<T> {
    return validateBody<T>(validator, schemaRef, await readJsonBody(request, limitBytes));
}
