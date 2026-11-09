import type {
    ApprovalOutcome,
    ApprovalStatus,
    AppEvent,
    ApprovalRequest,
    RunSnapshot,
    RunStatus,
    SessionId,
    WorkspaceId,
} from "@securecode/contracts";

export type RunConnectionState = "connected" | "disconnected" | "recovering";

export type RunOperation =
    { kind: "creating" } | { kind: "cancelling" } | { kind: "deciding_approval"; approvalId: string };

export interface RunViewState {
    sessionId: SessionId;
    workspaceId: WorkspaceId;
    snapshot: RunSnapshot | null;
    lastSequence: number;
    connection: RunConnectionState;
    operation: RunOperation | null;
    error: string | null;
    contextPlan: Extract<AppEvent, { type: "run.context_planned" }>["payload"] | null;
    pointerCreated: Extract<AppEvent, { type: "run.pointer_created" }>["payload"] | null;
    approvalDecision: ApprovalRequest | ApprovalOutcome | null;
}

export interface EventApplication {
    state: RunViewState;
    recoverSnapshot: boolean;
}

export function createRunViewState(sessionId: SessionId, workspaceId: WorkspaceId): RunViewState {
    return {
        sessionId,
        workspaceId,
        snapshot: null,
        lastSequence: 0,
        connection: "connected",
        operation: null,
        error: null,
        contextPlan: null,
        pointerCreated: null,
        approvalDecision: null,
    };
}

export function isTerminalRunStatus(status: RunStatus): boolean {
    return status === "completed" || status === "failed" || status === "cancelled";
}

export function applyRunSnapshot(state: RunViewState, snapshot: RunSnapshot): RunViewState {
    if (snapshot.session_id !== state.sessionId || snapshot.workspace_id !== state.workspaceId) {
        return state;
    }

    const current = state.snapshot;
    const sameRun = current?.run_id === snapshot.run_id;
    if (current && !sameRun && !isTerminalRunStatus(current.status)) {
        return state;
    }
    if (sameRun && current && isTerminalRunStatus(current.status) && current.status !== snapshot.status) {
        return state;
    }
    if (sameRun && current && snapshot.replay.last_sequence < state.lastSequence) {
        return state;
    }

    const latestOutcome = snapshot.approval_history?.at(-1) ?? null;
    return {
        ...state,
        snapshot,
        lastSequence: snapshot.replay.last_sequence,
        connection: "connected",
        operation: sameRun ? state.operation : null,
        error: null,
        contextPlan: sameRun ? state.contextPlan : null,
        pointerCreated: sameRun ? state.pointerCreated : null,
        approvalDecision: latestOutcome ? latestOutcome : sameRun ? state.approvalDecision : null,
    };
}

export function applyRunEvent(
    state: RunViewState,
    event: AppEvent,
    seenEventIds: ReadonlySet<string>,
): EventApplication {
    const snapshot = state.snapshot;
    if (
        !snapshot ||
        event.session_id !== state.sessionId ||
        event.workspace_id !== state.workspaceId ||
        event.run_id !== snapshot.run_id
    ) {
        return { state, recoverSnapshot: false };
    }

    if (event.type === "stream.replay_unavailable") {
        return {
            state: { ...state, connection: "recovering", error: null },
            recoverSnapshot: true,
        };
    }

    if (
        seenEventIds.has(event.event_id) ||
        event.sequence <= state.lastSequence ||
        isTerminalRunStatus(snapshot.status)
    ) {
        return { state, recoverSnapshot: false };
    }

    if (event.sequence !== state.lastSequence + 1) {
        return {
            state: { ...state, connection: "recovering", error: null },
            recoverSnapshot: true,
        };
    }

    const next = { ...state, lastSequence: event.sequence };
    switch (event.type) {
        case "run.status_changed":
            next.snapshot = {
                ...snapshot,
                status: event.payload.status,
                terminal: event.payload.terminal ?? snapshot.terminal,
            };
            break;
        case "run.output_delta":
            next.snapshot = {
                ...snapshot,
                answer: { ...snapshot.answer, text: snapshot.answer.text + event.payload.text },
            };
            break;
        case "run.tool_call_updated":
            next.snapshot = {
                ...snapshot,
                tool_calls: upsertBy(snapshot.tool_calls, event.payload.tool_call, (toolCall) => toolCall.tool_call_id),
            };
            break;
        case "run.approval_requested":
            next.snapshot = {
                ...snapshot,
                pending_approvals: upsertBy(
                    snapshot.pending_approvals,
                    event.payload.approval,
                    (approval) => approval.approval_id,
                ),
            };
            break;
        case "run.approval_resolved": {
            const approval = snapshot.pending_approvals.find(
                (pending) => pending.approval_id === event.payload.approval_id,
            );
            const status = toApprovalOutcomeStatus(event.payload.status);
            if (!status) {
                break;
            }
            const outcome: ApprovalOutcome | null = approval
                ? {
                      approval_id: approval.approval_id,
                      tool_call_id: approval.tool_call_id,
                      tool_name: approval.tool_name,
                      status,
                      decided_at: event.payload.decided_at,
                  }
                : null;
            next.snapshot = {
                ...snapshot,
                pending_approvals: snapshot.pending_approvals.filter(
                    (pending) => pending.approval_id !== event.payload.approval_id,
                ),
                approval_history: outcome
                    ? appendApprovalOutcome(snapshot.approval_history ?? [], outcome)
                    : snapshot.approval_history,
            };
            next.approvalDecision = approval
                ? { ...approval, status, decided_at: event.payload.decided_at }
                : state.approvalDecision;
            break;
        }
        case "run.pointer_created":
            next.pointerCreated = event.payload;
            break;
        case "run.context_planned":
            next.contextPlan = event.payload;
            break;
        default:
            return assertNever(event);
    }

    return { state: next, recoverSnapshot: false };
}

function upsertBy<T>(items: T[], item: T, keyOf: (value: T) => string): T[] {
    const key = keyOf(item);
    const index = items.findIndex((value) => keyOf(value) === key);
    if (index < 0) {
        return [...items, item];
    }
    return items.map((value, position) => (position === index ? item : value));
}

function appendApprovalOutcome(items: ApprovalOutcome[], outcome: ApprovalOutcome): ApprovalOutcome[] {
    return upsertBy(items, outcome, (item) => item.approval_id);
}

function toApprovalOutcomeStatus(status: ApprovalStatus): ApprovalOutcome["status"] | null {
    switch (status) {
        case "approved":
        case "rejected":
        case "expired":
        case "cancelled":
            return status;
        case "pending":
            return null;
    }
}

function assertNever(value: never): never {
    throw new Error(`Unsupported run event: ${String(value)}`);
}
