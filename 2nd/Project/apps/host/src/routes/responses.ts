/**
 * JSON response helpers. Error bodies always follow the ErrorResponse contract
 * with the HTTP status from contracts/common/error-codes.json.
 */
import type { ServerResponse } from "node:http";
import { loadErrorCodeTable, type ErrorCode, type ErrorDetails, type ErrorResponse } from "@securecode/contracts";

const ERROR_TABLE = loadErrorCodeTable();
const MAX_MESSAGE_CHARS = 500;

export interface RouteError {
    code: ErrorCode;
    message: string;
    details?: ErrorDetails;
    retryable?: boolean;
}

export function sendJson(response: ServerResponse, status: number, body: unknown): void {
    const payload = JSON.stringify(body);
    response.writeHead(status, {
        "content-type": "application/json; charset=utf-8",
        "content-length": Buffer.byteLength(payload),
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
    });
    response.end(payload);
}

export function buildErrorResponse(error: RouteError, requestId: string): { status: number; body: ErrorResponse } {
    const rule = ERROR_TABLE[error.code];
    const body: ErrorResponse = {
        schema_version: "1",
        error: {
            code: error.code,
            message: error.message.slice(0, MAX_MESSAGE_CHARS),
            retryable: error.retryable ?? rule.retryable,
            request_id: requestId,
            ...(error.details ? { details: error.details } : {}),
        },
    };
    return { status: rule.http_status, body };
}

export function sendError(response: ServerResponse, error: RouteError, requestId: string): void {
    const { status, body } = buildErrorResponse(error, requestId);
    sendJson(response, status, body);
}
