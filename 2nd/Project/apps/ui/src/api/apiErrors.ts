export type ApiFailureKind = "network" | "timeout" | "unauthorized" | "forbidden" | "server" | "contract" | "request";

export class ApiClientError extends Error {
    constructor(
        readonly kind: ApiFailureKind,
        message: string,
        readonly status?: number,
        readonly code?: string,
        readonly details?: Readonly<Record<string, string | number | boolean | null | undefined>>,
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
    BUDGET_EXCEEDED: "선택한 자료가 컨텍스트 예산을 초과했습니다. 범위나 입력을 줄이세요.",
    EXPIRED: "실행 결과의 보관 기간이 끝났습니다.",
    FORBIDDEN: "이 요청은 호스트 정책에 의해 거부되었습니다.",
    INDEX_NOT_READY: "색인이 준비되지 않았습니다. 색인 상태를 확인하세요.",
    INVALID_POINTER: "포인터가 더 이상 유효하지 않습니다.",
    INVALID_SELECTOR: "읽을 범위가 올바르지 않습니다.",
    IDEMPOTENCY_CONFLICT: "같은 요청 키에 다른 내용이 연결되어 있습니다. 상태를 확인한 뒤 다시 시도하세요.",
    NO_MATCH: "일치하는 결과가 없습니다.",
    NOT_FOUND: "요청한 항목을 찾을 수 없습니다.",
    PARSE_FAILED: "PDF를 처리하지 못했습니다.",
    PROTECTION_UNAVAILABLE: "필수 보호 기능이 준비되지 않아 실행을 시작할 수 없습니다.",
    RUN_ALREADY_ACTIVE: "현재 실행이 끝난 뒤 다시 시도하세요.",
    SOURCE_CHANGED: "원본이 변경되었습니다. 등록 자료를 갱신한 뒤 다시 시도하세요.",
    TOKENIZER_UNAVAILABLE: "토큰 계수기를 사용할 수 없어 예산을 검증하지 못했습니다.",
    UNSUPPORTED_FORMAT: "지원하지 않는 파일 형식입니다.",
    UNAUTHENTICATED: "연결 세션이 만료되었습니다. 일회용 연결 코드를 다시 입력하세요.",
    VALIDATION_FAILED: "요청 내용을 확인하고 다시 시도하세요.",
};

/** Server reasons that tell the user what to fix (host workspace-root and selector checks). */
const messagesByReason: Record<string, string> = {
    root_not_found: "경로가 존재하지 않습니다. 호스트 컴퓨터의 실제 폴더 경로를 입력하세요.",
    root_not_directory: "폴더가 아닌 파일 경로입니다. 프로젝트 폴더 경로를 입력하세요.",
    root_is_link: "심볼릭 링크 경로는 등록할 수 없습니다. 실제 폴더 경로를 입력하세요.",
    root_not_absolute: "절대 경로를 입력하세요.",
    root_is_filesystem_root: "드라이브 최상위 폴더는 등록할 수 없습니다.",
    path_outside_allowed_roots: "호스트 설정(SECURECODE_ALLOWED_WORKSPACE_ROOTS)이 허용한 위치 밖의 경로입니다.",
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

export function safeApiMessage(
    code: string | undefined,
    kind: ApiFailureKind,
    reason?: string | number | boolean | null,
): string {
    if (typeof reason === "string" && messagesByReason[reason]) {
        return messagesByReason[reason];
    }
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
