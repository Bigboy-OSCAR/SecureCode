/** Run cancellation and final approval-outcome policies shared by commands. */
import type { ApprovalOutcome, ApprovalRequest, RunSnapshot } from "@securecode/contracts";

export function isCancelable(snapshot: RunSnapshot): boolean {
    return snapshot.status === "queued" || snapshot.status === "running" || snapshot.status === "awaiting_approval";
}

export function toApprovalOutcomeStatus(status: ApprovalRequest["status"]): ApprovalOutcome["status"] | null {
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
