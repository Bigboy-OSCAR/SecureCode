/**
 * Error raised by the context-service client. It always carries a contract
 * ErrorCode so routes can forward it as an ApiError without leaking internals.
 */
import type { ApiError, ErrorCode, ErrorDetails } from "@securecode/contracts";

export class ContextServiceError extends Error {
    readonly code: ErrorCode;
    readonly retryable: boolean;
    readonly details: ErrorDetails | undefined;
    readonly upstreamRequestId: string | undefined;

    constructor(code: ErrorCode, message: string, retryable: boolean, details?: ErrorDetails, requestId?: string) {
        super(message);
        this.name = "ContextServiceError";
        this.code = code;
        this.retryable = retryable;
        this.details = details;
        this.upstreamRequestId = requestId;
    }

    static fromApiError(error: ApiError): ContextServiceError {
        return new ContextServiceError(error.code, error.message, error.retryable, error.details, error.request_id);
    }
}
