export type ApiFailureKind = "network" | "timeout" | "unauthorized" | "forbidden" | "server" | "contract" | "request";

export class ApiClientError extends Error {
    constructor(
        readonly kind: ApiFailureKind,
        message: string,
        readonly status?: number,
        readonly code?: string,
    ) {
        super(message);
        this.name = "ApiClientError";
    }
}

const messagesByCode: Record<string, string> = {
    APPROVAL_ALREADY_DECIDED: "이 승인 요청은 이미 처리되었습니다. 실행 상태를 다시 확인하세요.",
    APPROVAL_DIGEST_MISMATCH: "승인 내용이 변경되었습니다. 최신 내용을 다시 검토하세요.",
    APPROVAL_EXPIRED: "승인 기한이 지났습니다. 실행 상태를 다시 확인하세요.",
    BOOTSTRAP_CODE_EXPIRED: "연결 코드가 만료되었습니다. 실행 창에서 새 코드를 확인하세요.",
    BOOTSTRAP_CODE_INVALID: "연결 코드를 확인하고 다시 입력하세요.",
    FORBIDDEN: "이 요청은 호스트 정책에 의해 거부되었습니다.",
    IDEMPOTENCY_CONFLICT: "같은 요청 키에 다른 내용이 연결되어 있습니다. 상태를 확인한 뒤 다시 시도하세요.",
    INDEX_NOT_READY: "색인이 준비되지 않았습니다.",
    NOT_FOUND: "요청한 항목을 찾을 수 없습니다.",
    PROTECTION_UNAVAILABLE: "필수 보호 기능이 준비되지 않아 실행을 시작할 수 없습니다.",
    RUN_ALREADY_ACTIVE: "현재 실행이 끝난 뒤 다시 시도하세요.",
    UNAUTHENTICATED: "연결 세션이 만료되었습니다. 일회용 연결 코드를 다시 입력하세요.",
    VALIDATION_FAILED: "요청 내용을 확인하고 다시 시도하세요.",
};

export function toApiClientError(error: unknown): ApiClientError {
    if (error instanceof ApiClientError) {
        return error;
    }
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
        return new ApiClientError("timeout", "호스트 응답 시간이 초과되었습니다. 상태를 확인한 뒤 다시 시도하세요.");
    }
    return new ApiClientError("network", "호스트에 연결할 수 없습니다. 로컬 서비스 상태를 확인하세요.");
}

export function formatApiFailure(error: unknown, fallback: string): string {
    if (!(error instanceof ApiClientError)) {
        return fallback;
    }
    switch (error.kind) {
        case "network":
        case "timeout":
        case "unauthorized":
        case "forbidden":
        case "server":
        case "contract":
        case "request":
            return error.message || fallback;
    }
}

export function safeApiMessage(code: string | undefined, kind: ApiFailureKind): string {
    if (code && messagesByCode[code]) {
        return messagesByCode[code];
    }
    switch (kind) {
        case "network":
            return "호스트에 연결할 수 없습니다. 로컬 서비스 상태를 확인하세요.";
        case "timeout":
            return "호스트 응답 시간이 초과되었습니다. 상태를 확인한 뒤 다시 시도하세요.";
        case "unauthorized":
            return "연결 세션이 만료되었습니다. 일회용 연결 코드를 다시 입력하세요.";
        case "forbidden":
            return "이 요청은 호스트 정책에 의해 거부되었습니다.";
        case "server":
            return "호스트가 요청을 처리하지 못했습니다. 실행 상태를 다시 확인하세요.";
        case "contract":
            return "호스트 응답이 API 계약과 일치하지 않습니다.";
        case "request":
            return "요청 내용을 확인하고 다시 시도하세요.";
    }
}
