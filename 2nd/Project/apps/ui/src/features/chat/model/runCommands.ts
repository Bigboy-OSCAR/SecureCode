import type {
    ApprovalDecisionRequest,
    ApprovalId,
    ApprovalOutcome,
    ApprovalRequest,
    IdempotencyKey,
    ExplicitContextRef,
    RunCreateRequest,
    RunId,
    RunSnapshot,
} from "@securecode/contracts";
import type { RunClient } from "../../../api/runClient.js";
import { createIdempotencyKey } from "../../../api/runClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import { isCancelable, toApprovalOutcomeStatus } from "./runCommandPolicy.js";
import { isTerminalRunStatus, type RunViewState } from "./runState.js";

interface PendingCreate {
    prompt: string;
    contextRefs: ExplicitContextRef[];
    contextKey: string;
    key: IdempotencyKey;
    promise: Promise<boolean> | null;
}

interface RunCommandHost {
    getState(): RunViewState;
    publish(state: RunViewState): void;
    restore(snapshot: RunSnapshot): boolean;
    recoverSnapshot(runId: RunId, epoch: number): Promise<boolean>;
    getEpoch(): number;
    isCurrent(epoch: number): boolean;
}

export class RunCommands {
    private pendingCreate: PendingCreate | null = null;

    constructor(
        private readonly client: RunClient,
        private readonly host: RunCommandHost,
        private readonly makeIdempotencyKey: () => IdempotencyKey = createIdempotencyKey,
        private readonly now: () => number = Date.now,
    ) {}

    reset(): void {
        this.pendingCreate = null;
    }

    async createRun(prompt: string, contextRefs: ExplicitContextRef[] = []): Promise<boolean> {
        const contextKey = JSON.stringify(contextRefs);
        if (!prompt.trim() || prompt.length > 32_000) {
            return false;
        }
        if (this.pendingCreate?.promise) {
            return this.pendingCreate.prompt === prompt && this.pendingCreate.contextKey === contextKey
                ? this.pendingCreate.promise
                : false;
        }
        if (!this.canSubmitRun(prompt)) {
            return false;
        }

        const retry = this.pendingCreate;
        if (retry && (retry.prompt !== prompt || retry.contextKey !== contextKey)) {
            this.host.publish({ ...this.host.getState(), error: "이전 요청 결과를 확인한 뒤 새 질문을 시작하세요." });
            return false;
        }
        const create = retry ?? {
            prompt,
            contextRefs: structuredClone(contextRefs),
            contextKey,
            key: this.makeIdempotencyKey(),
            promise: null,
        };
        this.pendingCreate = create;
        const state = this.host.getState();
        const request: RunCreateRequest = {
            prompt,
            idempotency_key: create.key,
            ...(create.contextRefs.length ? { context_refs: create.contextRefs } : {}),
        };
        const sessionId = state.sessionId;
        const epoch = this.host.getEpoch();
        this.host.publish({ ...state, operation: { kind: "creating" }, error: null });

        const operation = this.client
            .createRun(sessionId, request)
            .then((snapshot) => {
                if (!this.host.isCurrent(epoch)) {
                    return false;
                }
                if (snapshot.session_id !== sessionId) {
                    this.host.publish({
                        ...this.host.getState(),
                        operation: null,
                        error: "실행 상태 응답을 확인할 수 없습니다.",
                    });
                    return false;
                }
                const restored = this.host.restore(snapshot);
                if (!restored) {
                    this.host.publish({
                        ...this.host.getState(),
                        error: "실행 상태 응답을 확인할 수 없습니다.",
                    });
                    return false;
                }
                this.pendingCreate = null;
                return true;
            })
            .catch((error: unknown) => {
                if (this.host.isCurrent(epoch)) {
                    this.host.publish({
                        ...this.host.getState(),
                        operation: null,
                        error: formatApiFailure(
                            error,
                            "요청 결과를 확인하지 못했습니다. 같은 질문으로 다시 확인하세요.",
                        ),
                    });
                }
                return false;
            })
            .finally(() => {
                if (this.host.isCurrent(epoch) && create.promise === operation) {
                    create.promise = null;
                    this.host.publish({ ...this.host.getState(), operation: null });
                }
            });
        create.promise = operation;
        return operation;
    }

    async cancelRun(): Promise<boolean> {
        const snapshot = this.host.getState().snapshot;
        if (!snapshot || !this.canCancelRun()) {
            return false;
        }
        const epoch = this.host.getEpoch();
        this.host.publish({ ...this.host.getState(), operation: { kind: "cancelling" }, error: null });
        try {
            const updated = await this.client.cancelRun(snapshot.run_id);
            if (!this.host.isCurrent(epoch)) {
                return false;
            }
            if (updated.run_id !== snapshot.run_id) {
                this.host.publish({ ...this.host.getState(), error: "취소 결과 확인이 필요합니다." });
                await this.host.recoverSnapshot(snapshot.run_id, epoch);
                return false;
            }
            return this.host.restore(updated);
        } catch (error) {
            if (this.host.isCurrent(epoch)) {
                this.host.publish({
                    ...this.host.getState(),
                    operation: null,
                    error: formatApiFailure(error, "취소 결과 확인이 필요합니다."),
                });
                await this.host.recoverSnapshot(snapshot.run_id, epoch);
            }
            return false;
        } finally {
            if (this.host.isCurrent(epoch) && this.host.getState().operation?.kind === "cancelling") {
                this.host.publish({ ...this.host.getState(), operation: null });
            }
        }
    }

    async decideApproval(approvalId: ApprovalId, decision: ApprovalDecisionRequest["decision"]): Promise<boolean> {
        const state = this.host.getState();
        const snapshot = state.snapshot;
        const approval = snapshot?.pending_approvals.find((item) => item.approval_id === approvalId);
        if (!snapshot || !approval || !this.canDecideApproval(approvalId, decision)) {
            this.host.publish({ ...state, error: "승인 요청의 상태와 검토 내용을 다시 확인하세요." });
            if (snapshot && approval && Date.parse(approval.expires_at) <= this.now()) {
                await this.host.recoverSnapshot(snapshot.run_id, this.host.getEpoch());
            }
            return false;
        }

        const request: ApprovalDecisionRequest = {
            decision,
            input_digest: approval.input_digest,
        };
        const epoch = this.host.getEpoch();
        this.host.publish({
            ...state,
            operation: { kind: "deciding_approval", approvalId },
            error: null,
        });
        try {
            const result = await this.client.decideApproval(snapshot.run_id, approvalId, request);
            if (!this.host.isCurrent(epoch)) {
                return false;
            }
            if (result.approval.approval_id !== approvalId) {
                this.host.publish({
                    ...this.host.getState(),
                    operation: null,
                    connection: "recovering",
                    error: "결정 결과 확인 중입니다.",
                });
                await this.host.recoverSnapshot(snapshot.run_id, epoch);
                return false;
            }
            if (result.approval.status !== (decision === "approve" ? "approved" : "rejected")) {
                throw new Error("Approval response did not confirm the requested decision.");
            }
            this.applyApprovalResponse(result.approval);
            return true;
        } catch (error) {
            if (this.host.isCurrent(epoch)) {
                this.host.publish({
                    ...this.host.getState(),
                    operation: null,
                    connection: "recovering",
                    error: formatApiFailure(error, "결정 결과 확인 중입니다."),
                });
                await this.host.recoverSnapshot(snapshot.run_id, epoch);
            }
            return false;
        } finally {
            if (this.host.isCurrent(epoch) && this.host.getState().operation?.kind === "deciding_approval") {
                this.host.publish({ ...this.host.getState(), operation: null });
            }
        }
    }

    canSubmitRun(prompt: string): boolean {
        if (this.pendingCreate && this.pendingCreate.prompt !== prompt) {
            return false;
        }
        const state = this.host.getState();
        const snapshot = state.snapshot;
        return (
            Boolean(prompt.trim()) &&
            prompt.length <= 32_000 &&
            state.connection === "connected" &&
            state.operation === null &&
            (!snapshot || isTerminalRunStatus(snapshot.status))
        );
    }

    canCancelRun(): boolean {
        const state = this.host.getState();
        const snapshot = state.snapshot;
        return Boolean(
            snapshot && state.connection === "connected" && state.operation === null && isCancelable(snapshot),
        );
    }

    canDecideApproval(approvalId: ApprovalId, decision: ApprovalDecisionRequest["decision"]): boolean {
        const state = this.host.getState();
        const snapshot = state.snapshot;
        const approval = snapshot?.pending_approvals.find((item) => item.approval_id === approvalId);
        return Boolean(
            snapshot &&
            approval &&
            state.connection === "connected" &&
            state.operation === null &&
            snapshot.status === "awaiting_approval" &&
            approval.status === "pending" &&
            Date.parse(approval.expires_at) > this.now() &&
            (decision === "reject" || (approval.review.reviewable && !approval.review.content_truncated)),
        );
    }

    private applyApprovalResponse(approval: ApprovalRequest): void {
        const state = this.host.getState();
        const snapshot = state.snapshot;
        if (!snapshot) {
            return;
        }
        const pending = snapshot.pending_approvals.filter((item) => item.approval_id !== approval.approval_id);
        const status = toApprovalOutcomeStatus(approval.status);
        const outcome: ApprovalOutcome | null =
            approval.decided_at && status
                ? {
                      approval_id: approval.approval_id,
                      tool_call_id: approval.tool_call_id,
                      tool_name: approval.tool_name,
                      status,
                      decided_at: approval.decided_at,
                  }
                : null;
        const history =
            outcome === null
                ? snapshot.approval_history
                : [
                      ...(snapshot.approval_history ?? []).filter((item) => item.approval_id !== approval.approval_id),
                      outcome,
                  ];
        this.host.publish({
            ...state,
            snapshot: { ...snapshot, pending_approvals: pending, approval_history: history },
            approvalDecision: approval,
        });
    }
}
