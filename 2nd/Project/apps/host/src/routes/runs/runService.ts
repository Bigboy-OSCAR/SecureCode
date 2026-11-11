/**
 * Run lifecycle over the SDK-independent AgentRuntime port: one active run per
 * session, idempotent creation, cancel through cancelling, approvals through
 * the broker, persisted snapshots and recovery of interrupted runs on restart.
 */
import type {
    AnswerCitation,
    ApprovalDecisionRequest,
    ApprovalRequest,
    ErrorCode,
    ProtectionState,
    RunCreateRequest,
    RunListResponse,
    RunSnapshot,
} from "@securecode/contracts";
import type { AgentRuntime, TurnOutcome, TurnSignal } from "../../cline/adapter/runtimePort.js";
import type { ContextAssembler } from "../../cline/context/contextAssembler.js";
import type { SessionContextStore } from "../../cline/context/sessionContext.js";
import type { ApprovalBroker } from "../../cline/permissions/approvalBroker.js";
import { missingProtections } from "../../cline/permissions/protections.js";
import { clipText, isoTime, newId, type Clock } from "../../security/ids.js";
import type { WorkspaceRegistry } from "../projects/workspaceRegistry.js";
import type { SessionStore } from "../sessions/sessionStore.js";
import type { IdempotencyStore } from "../shared/idempotency.js";
import { JsonFileStore } from "../shared/jsonFileStore.js";
import { paginate, type PageRequestInput } from "../shared/pagination.js";
import { RouteFailure } from "../shared/routeFailure.js";
import { RunEventLog } from "./eventLog.js";
import { isTerminal, toSnapshot, toSummary, type RunRecord, type SnapshotQuery } from "./runRecord.js";
import { RunRecorder } from "./runRecorder.js";

const PERSIST_DELAY_MS = 500;

export interface RunServiceDependencies {
    runtime: AgentRuntime;
    broker: ApprovalBroker;
    sessions: SessionStore;
    workspaces: WorkspaceRegistry;
    idempotency: IdempotencyStore;
    runsDirectory: string;
    clock: Clock;
    /** Plans each run's context (context.select) and returns the prompt with fragments inserted once. */
    assembler: ContextAssembler;
    sessionContext: SessionContextStore;
}

export function requireProtections(states: readonly ProtectionState[]): void {
    const missing = missingProtections(states);
    if (missing.length > 0) {
        throw new RouteFailure("PROTECTION_UNAVAILABLE", "required protections are not ready", {
            missing: missing.join(","),
        });
    }
}

export class RunService {
    private readonly recorders = new Map<string, RunRecorder>();
    private readonly store: JsonFileStore<RunRecord>;
    private readonly pendingWrites = new Map<string, NodeJS.Timeout>();
    /** Sessions whose run is being planned (context.select) before its record exists. */
    private readonly planning = new Set<string>();

    constructor(private readonly deps: RunServiceDependencies) {
        this.store = new JsonFileStore<RunRecord>(deps.runsDirectory);
        this.recover();
        deps.broker.setListener({
            requested: (_sessionId, approval) => this.recorders.get(approval.run_id)?.approvalRequested(approval),
            resolved: (_sessionId, approval, reasonCode) =>
                this.recorders.get(approval.run_id)?.approvalResolved(approval, reasonCode),
        });
    }

    async create(sessionId: string, request: RunCreateRequest): Promise<{ snapshot: RunSnapshot; created: boolean }> {
        const session = this.deps.sessions.get(sessionId);
        const lookup = this.deps.idempotency.lookup(`runs:${sessionId}`, request.idempotency_key, request);
        if (lookup.kind === "replay") return { snapshot: this.snapshot(lookup.resultId), created: false };
        requireProtections(this.deps.runtime.protections());
        if (session.status !== "active") throw new RouteFailure("VALIDATION_FAILED", "session is closed");
        if (session.active_run_id || this.planning.has(sessionId)) {
            throw new RouteFailure("RUN_ALREADY_ACTIVE", "this session already has an active run", {
                ...(session.active_run_id ? { active_run_id: session.active_run_id } : {}),
            });
        }
        const workspaceRoot = this.deps.workspaces.rootFor(session.workspace_id);
        this.planning.add(sessionId);
        let prompt: string;
        let inserted: AnswerCitation[];
        try {
            // Selection → bounded reads → counted plan; explicit choices that cannot be used refuse the run.
            const planned = await this.deps.assembler.forRun(session.workspace_id, sessionId, request);
            prompt = planned.prompt;
            inserted = planned.plan.fragments.flatMap<AnswerCitation>((fragment) => {
                const citation = fragment.provenance;
                return "related_locations" in citation
                    ? [
                          citation,
                          ...(citation.related_locations ?? []).map((location) => ({ ref: citation.ref, location })),
                      ]
                    : [citation];
            });
        } finally {
            this.planning.delete(sessionId);
        }
        if (this.deps.sessions.get(sessionId).active_run_id) {
            throw new RouteFailure("RUN_ALREADY_ACTIVE", "this session already has an active run");
        }
        const now = isoTime(this.deps.clock());
        const record: RunRecord = {
            run_id: newId("run"),
            session_id: sessionId,
            workspace_id: session.workspace_id,
            status: "queued",
            created_at: now,
            updated_at: now,
            prompt_preview: clipText(request.prompt.replace(/\s+/g, " ").trim(), 200),
            answer_text: "",
            answer_truncated: false,
            tool_calls: [],
            tool_calls_truncated: false,
            pending_approvals: [],
            approval_history: [],
            terminal: null,
            last_sequence: 0,
            citations: [],
        };
        const recorder = this.track(record);
        recorder.log.append("run.status_changed", { status: "queued", previous_status: null });
        this.persist(record, true);
        this.deps.sessions.setActiveRun(sessionId, record.run_id);
        this.deps.idempotency.remember(`runs:${sessionId}`, request.idempotency_key, lookup.bodyDigest, record.run_id);
        for (const citation of inserted) recorder.cite(citation);
        this.deps.sessionContext.beginRun(sessionId, (citation) => recorder.cite(citation));
        void this.execute(recorder, workspaceRoot, prompt);
        return { snapshot: this.snapshot(record.run_id), created: true };
    }

    hasActiveRuns(workspaceId?: string): boolean {
        for (const sessionId of this.planning)
            if (!workspaceId || this.deps.sessions.get(sessionId).workspace_id === workspaceId) return true;
        return [...this.recorders.values()].some(
            (recorder) => !recorder.terminal && (!workspaceId || recorder.record.workspace_id === workspaceId),
        );
    }

    snapshot(runId: string, query: SnapshotQuery = {}): RunSnapshot {
        const recorder = this.requireRun(runId);
        return toSnapshot(recorder.record, recorder.log.window(), query);
    }

    list(sessionId: string, page: PageRequestInput): RunListResponse {
        this.deps.sessions.get(sessionId);
        const records = [...this.recorders.values()]
            .map((recorder) => recorder.record)
            .filter((record) => record.session_id === sessionId)
            .sort((left, right) => left.created_at.localeCompare(right.created_at));
        const result = paginate(records.map(toSummary), `runs:${sessionId}`, page);
        return { schema_version: "1", items: result.items, page: result.page };
    }

    async cancel(runId: string): Promise<RunSnapshot> {
        const recorder = this.requireRun(runId);
        if (!recorder.terminal && recorder.record.status !== "cancelling") {
            recorder.setStatus("cancelling");
            await this.deps.runtime.abortTurn(recorder.record.session_id, "cancelled by user", runId);
        }
        return this.snapshot(runId);
    }

    decide(runId: string, approvalId: string, request: ApprovalDecisionRequest): ApprovalRequest {
        this.requireRun(runId);
        const result = this.deps.broker.decide(runId, approvalId, request.decision === "approve", request.input_digest);
        if (!result.ok) throw new RouteFailure(result.code, result.message);
        return result.approval;
    }

    eventLog(runId: string): RunEventLog {
        return this.requireRun(runId).log;
    }

    private async execute(recorder: RunRecorder, workspaceRoot: string, prompt: string): Promise<void> {
        const { record } = recorder;
        recorder.setStatus("running");
        let outcome: TurnOutcome;
        try {
            outcome = await this.deps.runtime.runTurn(
                {
                    workspaceId: record.workspace_id,
                    sessionId: record.session_id,
                    runId: record.run_id,
                    workspaceRoot,
                    prompt,
                },
                (signal) => this.apply(recorder, signal),
            );
        } catch {
            outcome = { finish: "failed", text: "", reasonCode: "SDK_UNAVAILABLE", message: "the SDK run failed" };
        }
        this.complete(recorder, outcome);
    }

    private apply(recorder: RunRecorder, signal: TurnSignal): void {
        switch (signal.kind) {
            case "output_delta":
                recorder.outputDelta(signal.messageId, signal.text);
                return;
            case "tool_started":
                recorder.toolCall({ tool_call_id: signal.toolCallId, tool_name: signal.toolName, phase: "running" });
                return;
            case "tool_finished":
                recorder.toolCall({
                    tool_call_id: signal.toolCallId,
                    tool_name: signal.toolName,
                    phase: signal.isError ? "failed" : "completed",
                    summary: signal.summary,
                    ...(signal.outputBytes === undefined ? {} : { output_bytes: signal.outputBytes }),
                    ...(signal.outputPointer ? { output_pointer: signal.outputPointer } : {}),
                });
                return;
            case "pointer_created":
                this.deps.sessionContext.pointerCreated(recorder.record.session_id, signal.pointer);
                recorder.pointerCreated(signal.toolCallId, signal.pointer, signal.byteSize);
                return;
        }
    }

    private complete(recorder: RunRecorder, outcome: TurnOutcome): void {
        if (recorder.record.answer_text === "" && outcome.text) {
            recorder.outputDelta(`${recorder.record.run_id}-final`, outcome.text);
        }
        // A user cancel wins even when the SDK finished the turn before the abort landed.
        const cancelRequested = recorder.record.status === "cancelling";
        if (outcome.finish === "completed" && !cancelRequested) {
            recorder.finish("completed");
        } else if (outcome.finish === "aborted" || cancelRequested) {
            recorder.finish("cancelled", "CANCELLED", "the run was cancelled");
        } else {
            recorder.finish("failed", outcome.reasonCode ?? "SDK_UNAVAILABLE", outcome.message);
        }
        this.deps.sessionContext.endRun(recorder.record.session_id);
        this.deps.sessions.setActiveRun(recorder.record.session_id, null);
    }

    /** Runs that were active when the host stopped cannot resume: mark them failed. */
    private recover(): void {
        for (const record of this.store.loadAll()) {
            const recorder = this.track(record, true);
            if (!isTerminal(record.status)) {
                const code: ErrorCode = "SERVICE_UNAVAILABLE";
                recorder.log.close();
                record.status = "failed";
                record.pending_approvals = [];
                record.terminal = {
                    status: "failed",
                    finished_at: isoTime(this.deps.clock()),
                    reason_code: code,
                    message: "the host restarted before the run finished",
                };
                for (const call of record.tool_calls) {
                    if (["requested", "awaiting_approval", "running"].includes(call.phase)) call.phase = "cancelled";
                }
                this.store.write(record.run_id, record);
            }
        }
    }

    private track(record: RunRecord, restored = false): RunRecorder {
        const log = new RunEventLog(
            { workspace_id: record.workspace_id, session_id: record.session_id, run_id: record.run_id },
            this.deps.clock,
            record.last_sequence,
            restored && isTerminal(record.status),
        );
        const recorder = new RunRecorder(record, log, (value, urgent) => this.persist(value, urgent), this.deps.clock);
        this.recorders.set(record.run_id, recorder);
        return recorder;
    }

    private persist(record: RunRecord, urgent: boolean): void {
        const recorder = this.recorders.get(record.run_id);
        if (recorder) record.last_sequence = recorder.log.lastSequence;
        const pending = this.pendingWrites.get(record.run_id);
        if (!urgent) {
            if (!pending) {
                const timer = setTimeout(() => this.persist(record, true), PERSIST_DELAY_MS);
                timer.unref();
                this.pendingWrites.set(record.run_id, timer);
            }
            return;
        }
        if (pending) clearTimeout(pending);
        this.pendingWrites.delete(record.run_id);
        this.store.write(record.run_id, record);
    }

    private requireRun(runId: string): RunRecorder {
        const recorder = this.recorders.get(runId);
        if (!recorder) throw new RouteFailure("NOT_FOUND", "run not found");
        return recorder;
    }
}
