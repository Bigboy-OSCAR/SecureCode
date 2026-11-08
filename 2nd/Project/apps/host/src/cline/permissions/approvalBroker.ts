/**
 * App-owned approval broker behind capabilities.requestToolApproval (3.1 S-01/C-03).
 * The SDK does not settle a pending approval on abort/stop, so the broker owns
 * the approval id, the sha256 input digest and the expiry, settles waiting
 * promises on timeout, run cancel or session close, and refuses late decisions.
 * It never imports the SDK: the adapter maps SDK requests onto ApprovalSubject.
 */
import type { ApprovalRequest, ApprovalReview, ErrorCode } from "@securecode/contracts";
import { canonicalJson, isoTime, newId, sha256Hex, type Clock } from "../../security/ids.js";

export interface ApprovalSubject {
    sessionId: string;
    runId: string;
    toolCallId: string;
    toolName: string;
    input: unknown;
    review: ApprovalReview;
}

export interface ApprovalVerdict {
    approved: boolean;
    reason?: string;
}

export interface ApprovalListener {
    requested(sessionId: string, approval: ApprovalRequest): void;
    resolved(sessionId: string, approval: ApprovalRequest, reasonCode?: ErrorCode): void;
}

export type DecisionResult =
    | { ok: true; approval: ApprovalRequest }
    | {
          ok: false;
          code: Extract<
              ErrorCode,
              | "NOT_FOUND"
              | "APPROVAL_EXPIRED"
              | "APPROVAL_ALREADY_DECIDED"
              | "APPROVAL_DIGEST_MISMATCH"
              | "VALIDATION_FAILED"
          >;
          message: string;
      };

interface PendingEntry {
    sessionId: string;
    approval: ApprovalRequest;
    expiresAtMs: number;
    settle: (verdict: ApprovalVerdict) => void;
    timer: NodeJS.Timeout;
}

const MAX_SETTLED_REMEMBERED = 2000;

export function inputDigest(input: unknown): string {
    return `sha256:${sha256Hex(canonicalJson(input))}`;
}

export class ApprovalBroker {
    private readonly pending = new Map<string, PendingEntry>();
    private readonly settled = new Map<string, ApprovalRequest>();
    private listener: ApprovalListener | null = null;

    constructor(
        private readonly timeoutMs: number,
        private readonly clock: Clock,
    ) {}

    setListener(listener: ApprovalListener): void {
        this.listener = listener;
    }

    request(subject: ApprovalSubject): Promise<ApprovalVerdict> {
        const now = this.clock();
        const approval: ApprovalRequest = {
            approval_id: newId("apr"),
            run_id: subject.runId,
            tool_call_id: subject.toolCallId,
            tool_name: subject.toolName,
            input_digest: inputDigest(subject.input),
            status: "pending",
            requested_at: isoTime(now),
            expires_at: isoTime(now + this.timeoutMs),
            review: subject.review,
        };
        return new Promise((resolve) => {
            const timer = setTimeout(
                () => this.finish(approval.approval_id, "expired", "APPROVAL_EXPIRED"),
                this.timeoutMs,
            );
            timer.unref();
            this.pending.set(approval.approval_id, {
                sessionId: subject.sessionId,
                approval,
                expiresAtMs: now + this.timeoutMs,
                settle: resolve,
                timer,
            });
            this.listener?.requested(subject.sessionId, approval);
        });
    }

    decide(runId: string, approvalId: string, approve: boolean, digest: string): DecisionResult {
        const entry = this.pending.get(approvalId);
        if (!entry) {
            const done = this.settled.get(approvalId);
            if (!done || done.run_id !== runId) return { ok: false, code: "NOT_FOUND", message: "approval not found" };
            if (done.status === "expired") return { ok: false, code: "APPROVAL_EXPIRED", message: "approval expired" };
            return { ok: false, code: "APPROVAL_ALREADY_DECIDED", message: "approval was already settled" };
        }
        if (entry.approval.run_id !== runId) return { ok: false, code: "NOT_FOUND", message: "approval not found" };
        if (this.clock() >= entry.expiresAtMs) {
            this.finish(approvalId, "expired", "APPROVAL_EXPIRED");
            return { ok: false, code: "APPROVAL_EXPIRED", message: "approval expired" };
        }
        if (digest !== entry.approval.input_digest) {
            return { ok: false, code: "APPROVAL_DIGEST_MISMATCH", message: "input digest does not match the request" };
        }
        if (approve && !entry.approval.review.reviewable) {
            return { ok: false, code: "VALIDATION_FAILED", message: "the tool input is too large to review" };
        }
        const approval = this.finish(
            approvalId,
            approve ? "approved" : "rejected",
            approve ? undefined : "APPROVAL_REJECTED",
        );
        return approval ? { ok: true, approval } : { ok: false, code: "APPROVAL_ALREADY_DECIDED", message: "settled" };
    }

    /** Settles every waiting approval of the session before core.abort/stop is called. */
    cancelSession(sessionId: string): void {
        for (const [approvalId, entry] of [...this.pending]) {
            if (entry.sessionId === sessionId) this.finish(approvalId, "cancelled", "CANCELLED");
        }
    }

    hasPending(sessionId: string): boolean {
        return [...this.pending.values()].some((entry) => entry.sessionId === sessionId);
    }

    private finish(
        approvalId: string,
        status: "approved" | "rejected" | "expired" | "cancelled",
        reasonCode?: ErrorCode,
    ): ApprovalRequest | null {
        const entry = this.pending.get(approvalId);
        if (!entry) return null;
        this.pending.delete(approvalId);
        clearTimeout(entry.timer);
        const approval: ApprovalRequest = { ...entry.approval, status, decided_at: isoTime(this.clock()) };
        this.remember(approval);
        entry.settle(
            status === "approved"
                ? { approved: true }
                : { approved: false, reason: `approval ${status} by SecureCode` },
        );
        this.listener?.resolved(entry.sessionId, approval, reasonCode);
        return approval;
    }

    private remember(approval: ApprovalRequest): void {
        this.settled.set(approval.approval_id, approval);
        if (this.settled.size > MAX_SETTLED_REMEMBERED) {
            const oldest = this.settled.keys().next().value;
            if (oldest !== undefined) this.settled.delete(oldest);
        }
    }
}
