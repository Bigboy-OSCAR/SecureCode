import type {
    ApprovalDecisionRequest,
    ApprovalId,
    AppEvent,
    IdempotencyKey,
    RunSnapshot,
    SessionId,
    WorkspaceId,
} from "@securecode/contracts";
import type { RunClient } from "../../../api/runClient.js";
import { createIdempotencyKey } from "../../../api/runClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import { RunCommands } from "./runCommands.js";
import {
    applyRunEvent,
    applyRunSnapshot,
    createRunViewState,
    isTerminalRunStatus,
    type RunViewState,
} from "./runState.js";

export type StateListener = () => void;

export class RunController {
    private state: RunViewState;
    private readonly listeners = new Set<StateListener>();
    private readonly seenEventIds = new Set<string>();
    private unsubscribe: (() => void) | null = null;
    private readonly commands: RunCommands;
    private epoch = 0;
    private disposed = false;

    constructor(
        private readonly client: RunClient,
        sessionId: SessionId,
        workspaceId: WorkspaceId,
        private readonly makeIdempotencyKey: () => IdempotencyKey = createIdempotencyKey,
        private readonly now: () => number = Date.now,
    ) {
        this.state = createRunViewState(sessionId, workspaceId);
        this.commands = new RunCommands(
            client,
            {
                getState: () => this.state,
                publish: (state) => this.publish(state),
                restore: (snapshot) => this.restore(snapshot),
                recoverSnapshot: (runId, epoch) => this.recoverSnapshot(runId, epoch),
                getEpoch: () => this.epoch,
                isCurrent: (epoch) => this.isCurrent(epoch),
            },
            makeIdempotencyKey,
            now,
        );
    }

    getSnapshot = (): RunViewState => this.state;

    subscribe = (listener: StateListener): (() => void) => {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    };

    restore(snapshot: RunSnapshot): boolean {
        if (this.disposed) {
            return false;
        }
        if (snapshot.session_id !== this.state.sessionId || snapshot.workspace_id !== this.state.workspaceId) {
            this.publish({ ...this.state, error: "실행 상태 응답의 범위가 일치하지 않습니다." });
            return false;
        }
        const previousRunId = this.state.snapshot?.run_id;
        const next = applyRunSnapshot(this.state, snapshot);
        if (next === this.state) {
            return false;
        }
        if (previousRunId !== snapshot.run_id) {
            this.seenEventIds.clear();
        }
        this.publish(next);
        this.attach(snapshot.run_id, snapshot.replay.last_sequence);
        return true;
    }

    setSession(sessionId: SessionId, workspaceId: WorkspaceId = this.state.workspaceId): void {
        if (sessionId === this.state.sessionId && workspaceId === this.state.workspaceId) {
            return;
        }
        this.epoch += 1;
        this.stopSubscription();
        this.commands.reset();
        this.seenEventIds.clear();
        this.publish(createRunViewState(sessionId, workspaceId));
    }

    createRun(prompt: string): Promise<boolean> {
        return this.disposed ? Promise.resolve(false) : this.commands.createRun(prompt);
    }

    cancelRun(): Promise<boolean> {
        return this.disposed ? Promise.resolve(false) : this.commands.cancelRun();
    }

    decideApproval(approvalId: ApprovalId, decision: ApprovalDecisionRequest["decision"]): Promise<boolean> {
        return this.disposed ? Promise.resolve(false) : this.commands.decideApproval(approvalId, decision);
    }

    receiveEvent(event: AppEvent): void {
        if (this.disposed) {
            return;
        }
        const result = applyRunEvent(this.state, event, this.seenEventIds);
        if (result.state !== this.state) {
            this.publish(result.state);
            if (!result.recoverSnapshot && event.type !== "stream.replay_unavailable") {
                this.seenEventIds.add(event.event_id);
            }
        }
        if (result.recoverSnapshot && this.state.snapshot) {
            void this.recoverSnapshot(this.state.snapshot.run_id, this.epoch);
        } else if (event.type === "run.status_changed" && event.payload.terminal && this.state.snapshot) {
            this.stopSubscription();
            void this.refreshCitations(this.state.snapshot.run_id, this.epoch);
        }
    }

    /** Citations are not streamed: after the terminal event, take the final list from the snapshot. */
    private async refreshCitations(runId: RunSnapshot["run_id"], epoch: number): Promise<void> {
        try {
            const snapshot = await this.client.getRun(runId);
            const current = this.state.snapshot;
            if (!this.isCurrent(epoch) || !current || current.run_id !== runId || snapshot.run_id !== runId) {
                return;
            }
            const { citations } = snapshot.answer;
            this.publish({
                ...this.state,
                snapshot: {
                    ...current,
                    answer: citations
                        ? { ...current.answer, citations, citations_page: snapshot.answer.citations_page }
                        : current.answer,
                },
            });
        } catch {
            // The run already finished; the answer stays shown without the late citation list.
        }
    }

    markDisconnected(error?: Error): void {
        if (!this.disposed) {
            this.publish({
                ...this.state,
                connection: "disconnected",
                error: error ? formatApiFailure(error, "이벤트 스트림 연결이 끊겼습니다.") : this.state.error,
            });
        }
    }

    async reconnect(): Promise<boolean> {
        const snapshot = this.state.snapshot;
        if (this.disposed) {
            return false;
        }
        if (!snapshot) {
            this.publish({ ...this.state, connection: "connected", error: null });
            return true;
        }
        return this.recoverSnapshot(snapshot.run_id, this.epoch);
    }

    canSubmitRun(prompt: string): boolean {
        return !this.disposed && this.commands.canSubmitRun(prompt);
    }

    canCancelRun(): boolean {
        return !this.disposed && this.commands.canCancelRun();
    }

    canDecideApproval(approvalId: ApprovalId, decision: ApprovalDecisionRequest["decision"]): boolean {
        return !this.disposed && this.commands.canDecideApproval(approvalId, decision);
    }

    isApprovalExpired(approvalId: ApprovalId): boolean {
        const approval = this.state.snapshot?.pending_approvals.find((item) => item.approval_id === approvalId);
        return approval ? Date.parse(approval.expires_at) <= this.now() : false;
    }

    dispose(): void {
        this.disposed = true;
        this.epoch += 1;
        this.stopSubscription();
        this.listeners.clear();
    }

    private async recoverSnapshot(runId: RunSnapshot["run_id"], epoch: number): Promise<boolean> {
        const sessionId = this.state.sessionId;
        this.publish({ ...this.state, connection: "recovering", error: null });
        try {
            const snapshot = await this.client.getRun(runId);
            if (
                !this.isCurrent(epoch) ||
                this.state.snapshot?.run_id !== runId ||
                snapshot.run_id !== runId ||
                snapshot.session_id !== sessionId ||
                snapshot.workspace_id !== this.state.workspaceId
            ) {
                if (this.isCurrent(epoch) && this.state.snapshot?.run_id === runId) {
                    this.publish({
                        ...this.state,
                        connection: "disconnected",
                        error: "최신 실행 상태의 범위가 일치하지 않습니다.",
                    });
                }
                return false;
            }
            // A live event may have advanced the view while this snapshot was in flight.
            if (snapshot.replay.last_sequence < this.state.lastSequence) {
                this.publish({ ...this.state, connection: "connected", error: null });
                this.attach(runId, this.state.lastSequence);
                return true;
            }
            return this.restore(snapshot);
        } catch (error) {
            if (this.isCurrent(epoch) && this.state.snapshot?.run_id === runId) {
                this.publish({
                    ...this.state,
                    connection: "disconnected",
                    error: formatApiFailure(error, "최신 실행 상태를 불러오지 못했습니다."),
                });
            }
            return false;
        }
    }

    private attach(runId: RunSnapshot["run_id"], sequence: number): void {
        this.stopSubscription();
        // A terminal snapshot already includes the final sequence. Reopening SSE after that
        // sequence yields an empty closed stream, which must not lock the next question.
        if (this.state.snapshot && isTerminalRunStatus(this.state.snapshot.status)) return;
        this.unsubscribe = this.client.subscribe(
            runId,
            sequence,
            (event) => this.receiveEvent(event),
            (error) => this.markDisconnected(error),
            () => {
                if (!this.disposed && this.state.snapshot?.run_id === runId) {
                    this.publish({ ...this.state, connection: "connected", error: null });
                }
            },
        );
    }

    private stopSubscription(): void {
        this.unsubscribe?.();
        this.unsubscribe = null;
    }

    private isCurrent(epoch: number): boolean {
        return !this.disposed && epoch === this.epoch;
    }

    private publish(next: RunViewState): void {
        if (this.disposed) {
            return;
        }
        this.state = next;
        this.listeners.forEach((listener) => listener());
    }
}
