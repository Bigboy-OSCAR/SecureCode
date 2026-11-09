import type {
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalId,
    AppEvent,
    RunCreateRequest,
    RunId,
    RunSnapshot,
    ApprovalRequest,
    Sequence,
    SessionId,
} from "@securecode/contracts";
import { fixtureAdapter } from "./fixtureAdapter.js";
import type { RunClient } from "./runClient.js";
import { boundedPreview } from "../features/shared/model/boundedPreview.js";

interface IdempotentRun {
    prompt: string;
    snapshot: RunSnapshot;
}

export class FixtureRunClient implements RunClient {
    private readonly snapshots = new Map<RunId, RunSnapshot>();
    private readonly idempotentRuns = new Map<string, IdempotentRun>();
    private readonly subscriptions = new Map<
        RunId,
        { onEvent: (event: AppEvent) => void; onDisconnect: () => void; afterSequence: Sequence }
    >();
    private runNumber = 0;

    async createRun(sessionId: SessionId, request: RunCreateRequest): Promise<RunSnapshot> {
        const existing = this.idempotentRuns.get(request.idempotency_key);
        if (existing) {
            if (existing.prompt !== request.prompt) {
                throw new Error("IDEMPOTENCY_CONFLICT");
            }
            return existing.snapshot;
        }

        const template = fixtureAdapter.runs[0]!;
        if (sessionId !== template.session_id) {
            throw new Error("Fixture session is unavailable.");
        }
        const activeRun = [...this.snapshots.values()].find(
            (run) =>
                run.session_id === sessionId &&
                run.status !== "completed" &&
                run.status !== "failed" &&
                run.status !== "cancelled",
        );
        if (activeRun) {
            throw new Error("RUN_ALREADY_ACTIVE");
        }
        this.runNumber += 1;
        const runId = this.runNumber === 1 ? template.run_id : `${template.run_id}${this.runNumber}`;
        const snapshot: RunSnapshot = {
            ...template,
            run_id: runId,
            prompt_preview: boundedPreview(request.prompt, 280),
            pending_approvals: template.pending_approvals.map((approval) => ({
                ...approval,
                approval_id: this.runNumber === 1 ? approval.approval_id : `${approval.approval_id}${this.runNumber}`,
                run_id: runId,
            })),
        };
        this.snapshots.set(snapshot.run_id, snapshot);
        this.idempotentRuns.set(request.idempotency_key, { prompt: request.prompt, snapshot });
        return snapshot;
    }

    async getRun(runId: RunId): Promise<RunSnapshot> {
        const snapshot = this.snapshots.get(runId) ?? fixtureAdapter.runs.find((run) => run.run_id === runId);
        if (!snapshot) {
            throw new Error("Run fixture is unavailable.");
        }
        return snapshot;
    }

    async cancelRun(runId: RunId): Promise<RunSnapshot> {
        const cancelledFixture = fixtureAdapter.runs.find((run) => run.status === "cancelled");
        const current = this.snapshots.get(runId);
        if (!cancelledFixture || !current) {
            throw new Error("Cancellation fixture is unavailable.");
        }
        const cancelled: RunSnapshot = {
            ...cancelledFixture,
            run_id: runId,
            session_id: current.session_id,
            workspace_id: current.workspace_id,
        };
        this.snapshots.set(runId, cancelled);
        return cancelled;
    }

    async decideApproval(
        runId: RunId,
        approvalId: ApprovalId,
        request: ApprovalDecisionRequest,
    ): Promise<ApprovalDecisionResponse> {
        const snapshot = await this.getRun(runId);
        const pending = snapshot.pending_approvals.find((approval) => approval.approval_id === approvalId);
        if (!pending || pending.input_digest !== request.input_digest) {
            throw new Error("APPROVAL_ALREADY_DECIDED");
        }
        const status: ApprovalRequest["status"] = request.decision === "approve" ? "approved" : "rejected";
        const approval = {
            ...pending,
            status,
            decided_at: "2026-11-04T09:02:00Z",
        };
        this.snapshots.set(runId, {
            ...snapshot,
            pending_approvals: snapshot.pending_approvals.filter((item) => item.approval_id !== approvalId),
            approval_history: [
                ...(snapshot.approval_history ?? []).filter((item) => item.approval_id !== approvalId),
                {
                    approval_id: approval.approval_id,
                    tool_call_id: approval.tool_call_id,
                    tool_name: approval.tool_name,
                    status: approval.status,
                    decided_at: approval.decided_at,
                },
            ],
        });
        return { schema_version: snapshot.schema_version, approval };
    }

    subscribe(
        runId: RunId,
        afterSequence: Sequence,
        onEvent: (event: AppEvent) => void,
        onDisconnect: () => void,
    ): () => void {
        const subscription = { onEvent, onDisconnect, afterSequence };
        this.subscriptions.set(runId, subscription);
        return () => {
            if (this.subscriptions.get(runId) === subscription) {
                this.subscriptions.delete(runId);
            }
        };
    }

    emit(event: AppEvent): void {
        this.subscriptions.get(event.run_id)?.onEvent(event);
    }

    disconnect(runId: RunId): void {
        this.subscriptions.get(runId)?.onDisconnect();
    }

    getLastSubscribedSequence(runId: RunId): Sequence | null {
        return this.subscriptions.get(runId)?.afterSequence ?? null;
    }
}

export const fixtureRunClient = new FixtureRunClient();
