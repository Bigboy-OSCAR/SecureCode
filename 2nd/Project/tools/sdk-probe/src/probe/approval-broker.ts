/**
 * App-owned approval broker for `capabilities.requestToolApproval`.
 * SDK 0.2.0 does not settle a pending approval on abort/stop, so the host must:
 * create an approval id + input digest + expiry, reject on timeout or session
 * cancel, and refuse late decisions. Probe-sized version of the 3.5 design.
 */
import { createHash, randomUUID } from "node:crypto";
import type { ToolApprovalRequest, ToolApprovalResult } from "@cline/sdk";

export type ApprovalDecisionOutcome = "applied" | "unknown_or_settled" | "digest_mismatch";

interface PendingApproval {
    sessionId: string;
    inputDigest: string;
    expiresAt: number;
    settle: (result: ToolApprovalResult) => void;
}

export interface ApprovalTicket {
    approvalId: string;
    sessionId: string;
    toolName: string;
    inputDigest: string;
    expiresAt: number;
}

export function digestToolInput(input: unknown): string {
    return createHash("sha256")
        .update(JSON.stringify(input) ?? "null")
        .digest("hex");
}

export class ApprovalBroker {
    readonly tickets: ApprovalTicket[] = [];
    private readonly pending = new Map<string, PendingApproval>();

    constructor(private readonly timeoutMs: number) {}

    readonly requestToolApproval = (request: ToolApprovalRequest): Promise<ToolApprovalResult> => {
        const approvalId = randomUUID();
        const inputDigest = digestToolInput(request.input);
        const expiresAt = Date.now() + this.timeoutMs;

        return new Promise((resolve) => {
            const timer = setTimeout(
                () => this.settle(approvalId, { approved: false, reason: "approval timed out" }),
                this.timeoutMs,
            );
            const settle = (result: ToolApprovalResult): void => {
                clearTimeout(timer);
                resolve(result);
            };
            this.pending.set(approvalId, { sessionId: request.sessionId, inputDigest, expiresAt, settle });
            this.tickets.push({
                approvalId,
                sessionId: request.sessionId,
                toolName: request.toolName,
                inputDigest,
                expiresAt,
            });
        });
    };

    decide(approvalId: string, inputDigest: string, approved: boolean): ApprovalDecisionOutcome {
        const entry = this.pending.get(approvalId);
        if (!entry || entry.expiresAt < Date.now()) {
            return "unknown_or_settled";
        }
        if (entry.inputDigest !== inputDigest) {
            return "digest_mismatch";
        }
        this.settle(approvalId, approved ? { approved: true } : { approved: false, reason: "rejected by user" });
        return "applied";
    }

    /** Called by the host before `core.abort`/`core.stop` so the run can unwind. */
    cancelSession(sessionId: string, reason: string): number {
        let cancelledCount = 0;
        for (const [approvalId, entry] of this.pending) {
            if (entry.sessionId === sessionId) {
                this.settle(approvalId, { approved: false, reason });
                cancelledCount += 1;
            }
        }
        return cancelledCount;
    }

    private settle(approvalId: string, result: ToolApprovalResult): void {
        const entry = this.pending.get(approvalId);
        if (!entry) {
            return;
        }
        this.pending.delete(approvalId);
        entry.settle(result);
    }
}
