import type {
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalId,
    BootstrapRequest,
    BootstrapResponse,
    HealthResponse,
    RunCreateRequest,
    RunId,
    RunSnapshot,
    Session,
    SessionCreateRequest,
    SessionId,
    SettingsResponse,
    Workspace,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
} from "@securecode/contracts";
import { ApiClientError, safeApiMessage } from "./apiErrors.js";
import { InvalidApiPayloadError, parseApiPayload, serializeApiRequest } from "./mappers/contractMapper.js";

export type ApiFetch = typeof fetch;

export class ApiHttpClient {
    constructor(
        private readonly baseUrl = "/api/v1",
        private readonly fetcher: ApiFetch = fetch,
        private readonly timeoutMs = 15000,
    ) {}

    bootstrap(request: BootstrapRequest): Promise<BootstrapResponse> {
        return this.post("auth/bootstrap", "bootstrapResponse", request, "bootstrapRequest");
    }

    getHealth(): Promise<HealthResponse> {
        return this.get("health", "healthResponse");
    }

    getSettings(): Promise<SettingsResponse> {
        return this.get("settings", "settingsResponse");
    }

    listWorkspaces(cursor?: string): Promise<WorkspaceListResponse> {
        const query = new URLSearchParams({ limit: "100" });
        if (cursor) {
            query.set("cursor", cursor);
        }
        return this.get(`workspaces?${query}`, "workspaceListResponse");
    }

    createWorkspace(request: WorkspaceCreateRequest): Promise<Workspace> {
        return this.post("workspaces", "workspace", request, "workspaceCreateRequest");
    }

    createSession(request: SessionCreateRequest): Promise<Session> {
        return this.post("sessions", "session", request, "sessionCreateRequest");
    }

    createRun(sessionId: SessionId, request: RunCreateRequest): Promise<RunSnapshot> {
        return this.post(`sessions/${encodeURIComponent(sessionId)}/runs`, "runSnapshot", request, "runCreateRequest");
    }

    getRun(runId: RunId): Promise<RunSnapshot> {
        return this.get(`runs/${encodeURIComponent(runId)}`, "runSnapshot");
    }

    cancelRun(runId: RunId): Promise<RunSnapshot> {
        return this.post(`runs/${encodeURIComponent(runId)}/cancel`, "runSnapshot", undefined);
    }

    decideApproval(
        runId: RunId,
        approvalId: ApprovalId,
        request: ApprovalDecisionRequest,
    ): Promise<ApprovalDecisionResponse> {
        return this.post(
            `runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`,
            "approvalDecisionResponse",
            request,
            "approvalDecisionRequest",
        );
    }

    private get<T>(path: string, responseSchema: Parameters<typeof parseApiPayload<T>>[0]): Promise<T> {
        return this.request("GET", path, undefined, responseSchema);
    }

    private post<T>(
        path: string,
        responseSchema: Parameters<typeof parseApiPayload<T>>[0],
        body: unknown,
        requestSchema?: Parameters<typeof parseApiPayload<T>>[0],
    ): Promise<T> {
        const wireBody = requestSchema ? serializeApiRequest(requestSchema, body) : body;
        return this.request("POST", path, wireBody, responseSchema);
    }

    private async request<T>(
        method: "GET" | "POST",
        path: string,
        body: unknown,
        responseSchema: Parameters<typeof parseApiPayload<T>>[0],
    ): Promise<T> {
        let response: Response;
        try {
            response = await this.fetcher(`${this.baseUrl.replace(/\/$/, "")}/${path}`, {
                method,
                credentials: "same-origin",
                headers: {
                    accept: "application/json",
                    ...(body === undefined ? {} : { "content-type": "application/json" }),
                },
                ...(body === undefined ? {} : { body: JSON.stringify(body) }),
                signal: AbortSignal.timeout(this.timeoutMs),
            });
        } catch (error) {
            throw toTransportError(error);
        }

        const payload = await readJson(response);
        if (!response.ok) {
            throw mapHttpError(response.status, payload);
        }
        try {
            return parseApiPayload<T>(responseSchema, payload);
        } catch (error) {
            if (error instanceof InvalidApiPayloadError) {
                throw new ApiClientError("contract", "호스트 응답이 API 계약과 일치하지 않습니다.", response.status);
            }
            throw error;
        }
    }
}

async function readJson(response: Response): Promise<unknown> {
    try {
        return await response.json();
    } catch {
        throw new ApiClientError("contract", "호스트가 유효한 JSON 응답을 반환하지 않았습니다.", response.status);
    }
}

function mapHttpError(status: number, payload: unknown): ApiClientError {
    let code: string | undefined;
    try {
        const response = parseApiPayload<{ error: { code: string } }>("errorResponse", payload);
        code = response.error.code;
    } catch {
        return new ApiClientError("contract", "호스트 오류 응답이 API 계약과 일치하지 않습니다.", status);
    }

    if (status === 401) {
        return new ApiClientError("unauthorized", safeApiMessage(code, "unauthorized"), status, code);
    }
    if (status === 403) {
        return new ApiClientError("forbidden", safeApiMessage(code, "forbidden"), status, code);
    }
    if (status >= 500) {
        return new ApiClientError("server", safeApiMessage(code, "server"), status, code);
    }
    return new ApiClientError("request", safeApiMessage(code, "request"), status, code);
}

function toTransportError(error: unknown): ApiClientError {
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
        return new ApiClientError("timeout", "호스트 응답 시간이 초과되었습니다. 상태를 확인한 뒤 다시 시도하세요.");
    }
    return new ApiClientError("network", "호스트에 연결할 수 없습니다. 로컬 서비스 상태를 확인하세요.");
}
