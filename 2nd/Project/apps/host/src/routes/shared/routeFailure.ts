/**
 * Typed failure thrown by route handlers and host services. The server turns it
 * into the contract ErrorResponse, so handlers never write error bodies by hand.
 */
import type { ErrorCode, ErrorDetails } from "@securecode/contracts";
import type { RouteError } from "../responses.js";

export class RouteFailure extends Error {
    readonly error: RouteError;

    constructor(code: ErrorCode, message: string, details?: ErrorDetails, retryable?: boolean) {
        super(message);
        this.name = "RouteFailure";
        this.error = {
            code,
            message,
            ...(details ? { details } : {}),
            ...(retryable === undefined ? {} : { retryable }),
        };
    }
}
