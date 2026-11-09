import type {
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalId,
    AppEvent,
    RunCreateRequest,
    RunId,
    RunSnapshot,
    Sequence,
    SessionId,
} from "@securecode/contracts";
import { ApiHttpClient } from "./httpClient.js";
import type { RunClient } from "./runClient.js";
import { SseClient } from "./events/sseClient.js";

export class HttpRunClient implements RunClient {
    constructor(
        private readonly http: ApiHttpClient = new ApiHttpClient(),
        private readonly sse: SseClient = new SseClient(),
    ) {}

    createRun(sessionId: SessionId, request: RunCreateRequest): Promise<RunSnapshot> {
        return this.http.createRun(sessionId, request);
    }

    getRun(runId: RunId): Promise<RunSnapshot> {
        return this.http.getRun(runId);
    }

    cancelRun(runId: RunId): Promise<RunSnapshot> {
        return this.http.cancelRun(runId);
    }

    decideApproval(
        runId: RunId,
        approvalId: ApprovalId,
        request: ApprovalDecisionRequest,
    ): Promise<ApprovalDecisionResponse> {
        return this.http.decideApproval(runId, approvalId, request);
    }

    subscribe(
        runId: RunId,
        afterSequence: Sequence,
        onEvent: (event: AppEvent) => void,
        onDisconnect: (error?: Error) => void,
        onReconnect?: () => void,
    ): () => void {
        return this.sse.subscribe(runId, afterSequence, onEvent, onDisconnect, onReconnect);
    }
}
