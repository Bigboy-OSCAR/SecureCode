import type {
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalId,
    AppEvent,
    IdempotencyKey,
    RunCreateRequest,
    RunId,
    RunSnapshot,
    Sequence,
    SessionId,
} from "@securecode/contracts";

export interface RunClient {
    createRun(sessionId: SessionId, request: RunCreateRequest): Promise<RunSnapshot>;
    getRun(runId: RunId): Promise<RunSnapshot>;
    cancelRun(runId: RunId): Promise<RunSnapshot>;
    decideApproval(
        runId: RunId,
        approvalId: ApprovalId,
        request: ApprovalDecisionRequest,
    ): Promise<ApprovalDecisionResponse>;
    subscribe(
        runId: RunId,
        afterSequence: Sequence,
        onEvent: (event: AppEvent) => void,
        onDisconnect: () => void,
    ): () => void;
}

export function createIdempotencyKey(): IdempotencyKey {
    return `ui-${globalThis.crypto.randomUUID()}`;
}
