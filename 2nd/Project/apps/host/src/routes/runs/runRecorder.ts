/**
 * Applies run facts to the record and the event log together, so the
 * snapshot and the SSE stream never disagree. Enforces the status machine:
 * queued → running ⇄ awaiting_approval → (cancelling) → terminal, and a
 * terminal status never changes again (late SDK facts are dropped).
 */
import type {
    AnswerCitation,
    ApprovalRequest,
    ErrorCode,
    RunStatus,
    TerminalRunStatus,
    ToolCallPhase,
    ToolCallSummary,
} from "@securecode/contracts";
import { clipText, isoTime, type Clock } from "../../security/ids.js";
import type { RunEventLog } from "./eventLog.js";
import {
    ANSWER_MAX_CHARS,
    CITATIONS_MAX,
    citationKey,
    isTerminal,
    PENDING_APPROVALS_MAX,
    TOOL_CALLS_MAX,
    type RunRecord,
} from "./runRecord.js";

const DELTA_MAX_CHARS = 4096;
const FINAL_TOOL_PHASES: ReadonlySet<ToolCallPhase> = new Set(["completed", "failed", "rejected", "cancelled"]);

export class RunRecorder {
    constructor(
        readonly record: RunRecord,
        readonly log: RunEventLog,
        private readonly persist: (record: RunRecord, urgent: boolean) => void,
        private readonly clock: Clock,
    ) {}

    get terminal(): boolean {
        return isTerminal(this.record.status);
    }

    setStatus(next: RunStatus): void {
        const previous = this.record.status;
        if (this.terminal || previous === next || isTerminal(next)) return;
        if (previous === "cancelling" && next !== "cancelling") return;
        this.record.status = next;
        this.touch();
        this.log.append("run.status_changed", { status: next, previous_status: previous });
        this.persist(this.record, true);
    }

    outputDelta(messageId: string, text: string): void {
        if (this.terminal || text.length === 0) return;
        const room = ANSWER_MAX_CHARS - this.record.answer_text.length;
        if (room <= 0) {
            this.record.answer_truncated = true;
        } else {
            const kept = clipText(text, room);
            this.record.answer_text += kept;
            this.record.answer_truncated ||= kept.length < text.length;
        }
        for (let offset = 0; offset < text.length;) {
            const piece = clipText(text.slice(offset), DELTA_MAX_CHARS);
            this.log.append("run.output_delta", { message_id: messageId.slice(0, 128), text: piece });
            offset += piece.length || 1;
        }
        this.touch();
        this.persist(this.record, false);
    }

    toolCall(update: Omit<ToolCallSummary, "summary"> & { summary?: string }): void {
        if (this.terminal) return;
        const calls = this.record.tool_calls;
        let current = calls.find((call) => call.tool_call_id === update.tool_call_id);
        // A final phase (and its summary, e.g. a refusal reason) is never overwritten by later SDK events.
        if (current && FINAL_TOOL_PHASES.has(current.phase)) return;
        if (!current) {
            if (calls.length >= TOOL_CALLS_MAX) {
                this.record.tool_calls_truncated = true;
            } else {
                current = {
                    tool_call_id: update.tool_call_id,
                    tool_name: update.tool_name,
                    phase: update.phase,
                    summary: "",
                };
                calls.push(current);
            }
        }
        const next: ToolCallSummary = {
            ...(current ?? { tool_call_id: update.tool_call_id, tool_name: update.tool_name, summary: "" }),
            ...update,
            summary: clipText(update.summary ?? current?.summary ?? `${update.tool_name} ${update.phase}`, 500),
        };
        if (current) Object.assign(current, next);
        this.touch();
        this.log.append("run.tool_call_updated", { tool_call: next });
        this.persist(this.record, true);
    }

    approvalRequested(approval: ApprovalRequest): void {
        if (this.terminal) return;
        if (this.record.pending_approvals.length < PENDING_APPROVALS_MAX) this.record.pending_approvals.push(approval);
        this.log.append("run.approval_requested", { approval });
        this.toolCall({
            tool_call_id: approval.tool_call_id,
            tool_name: approval.tool_name,
            phase: "awaiting_approval",
            summary: approval.review.summary,
        });
        this.setStatus("awaiting_approval");
    }

    approvalResolved(approval: ApprovalRequest, reasonCode?: ErrorCode): void {
        if (this.terminal || approval.status === "pending") return;
        this.record.pending_approvals = this.record.pending_approvals.filter(
            (item) => item.approval_id !== approval.approval_id,
        );
        this.record.approval_history.push({
            approval_id: approval.approval_id,
            tool_call_id: approval.tool_call_id,
            tool_name: approval.tool_name,
            status: approval.status,
            decided_at: approval.decided_at ?? isoTime(this.clock()),
        });
        this.log.append("run.approval_resolved", {
            approval_id: approval.approval_id,
            status: approval.status,
            decided_at: approval.decided_at ?? isoTime(this.clock()),
            ...(reasonCode ? { reason_code: reasonCode } : {}),
        });
        const phase: ToolCallPhase =
            approval.status === "approved" ? "running" : approval.status === "cancelled" ? "cancelled" : "rejected";
        this.toolCall({
            tool_call_id: approval.tool_call_id,
            tool_name: approval.tool_name,
            phase,
            summary: `${approval.tool_name} ${approval.status}`,
        });
        if (this.record.pending_approvals.length === 0 && this.record.status === "awaiting_approval") {
            this.setStatus("running");
        }
    }

    pointerCreated(toolCallId: string, pointer: string, byteSize: number): void {
        if (this.terminal) return;
        this.log.append("run.pointer_created", {
            pointer,
            kind: "runtime",
            byte_size: byteSize,
            tool_call_id: toolCallId,
        });
    }

    /** Adds one verified input of this run (deduplicated, bounded); the snapshot pages them. */
    cite(citation: AnswerCitation): void {
        if (this.terminal) return;
        const cited = (this.record.citations ??= []);
        const key = citationKey(citation);
        if (cited.length >= CITATIONS_MAX || cited.some((item) => citationKey(item) === key)) return;
        cited.push(citation);
        this.persist(this.record, false);
    }

    finish(status: TerminalRunStatus, reasonCode?: ErrorCode, message?: string): void {
        if (this.terminal) return;
        const previous = this.record.status;
        const finishedAt = isoTime(this.clock());
        for (const call of this.record.tool_calls) {
            if (!FINAL_TOOL_PHASES.has(call.phase)) call.phase = status === "completed" ? "completed" : "cancelled";
        }
        this.record.pending_approvals = [];
        this.record.status = status;
        this.record.terminal = {
            status,
            finished_at: finishedAt,
            ...(reasonCode ? { reason_code: reasonCode } : {}),
            ...(message ? { message: clipText(message, 500) } : {}),
        };
        this.record.updated_at = finishedAt;
        this.log.append("run.status_changed", { status, previous_status: previous, terminal: this.record.terminal });
        this.record.last_sequence = this.log.lastSequence;
        this.log.close();
        this.persist(this.record, true);
    }

    private touch(): void {
        this.record.updated_at = isoTime(this.clock());
        this.record.last_sequence = this.log.lastSequence;
    }
}
