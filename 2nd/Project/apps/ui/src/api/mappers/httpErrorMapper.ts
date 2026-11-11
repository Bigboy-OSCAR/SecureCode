/** Validate server error envelopes and convert HTTP status into safe client-facing failures. */
import type { ErrorResponse } from "@securecode/contracts";
import { ApiClientError, safeApiMessage } from "../apiErrors.js";
import { parseApiPayload } from "./contractMapper.js";

export function mapHttpError(status: number, payload: unknown): ApiClientError {
    let code: string | undefined;
    let details: ErrorResponse["error"]["details"];
    try {
        const response = parseApiPayload<ErrorResponse>("errorResponse", payload);
        code = response.error.code;
        details = response.error.details;
    } catch {
        return new ApiClientError("contract", "호스트 오류 응답이 API 계약과 일치하지 않습니다.", status);
    }

    if (status === 401) {
        return new ApiClientError(
            "unauthorized",
            safeApiMessage(code, "unauthorized", details?.reason),
            status,
            code,
            details,
        );
    }
    if (status === 403) {
        return new ApiClientError(
            "forbidden",
            safeApiMessage(code, "forbidden", details?.reason),
            status,
            code,
            details,
        );
    }
    if (status >= 500) {
        return new ApiClientError("server", safeApiMessage(code, "server", details?.reason), status, code, details);
    }
    return new ApiClientError("request", safeApiMessage(code, "request", details?.reason), status, code, details);
}
