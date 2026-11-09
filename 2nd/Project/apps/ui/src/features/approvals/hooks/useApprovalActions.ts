import { useState } from "react";
import type { ApprovalId } from "@securecode/contracts";
import type { RunController } from "../../chat/model/runController.js";
import type { RunViewState } from "../../chat/model/runState.js";

export type ApprovalIntent = "approve" | "reject";

export function useApprovalActions(
    controller: RunController,
    state: RunViewState,
): {
    intent: ApprovalIntent | null;
    approvalId: ApprovalId | null;
    open: (intent: ApprovalIntent) => void;
    close: () => void;
    confirm: () => void;
} {
    const [reviewed, setReviewed] = useState<{
        intent: ApprovalIntent;
        approvalId: ApprovalId;
        inputDigest: string;
    } | null>(null);
    const approval = state.snapshot?.pending_approvals[0];
    const currentReview =
        approval?.approval_id === reviewed?.approvalId && approval?.input_digest === reviewed?.inputDigest
            ? reviewed
            : null;

    return {
        intent: currentReview?.intent ?? null,
        approvalId: currentReview?.approvalId ?? null,
        open: (intent) => {
            if (approval) {
                setReviewed({ intent, approvalId: approval.approval_id, inputDigest: approval.input_digest });
            }
        },
        close: () => setReviewed(null),
        confirm: () => {
            if (currentReview) {
                void controller.decideApproval(currentReview.approvalId, currentReview.intent);
                setReviewed(null);
            }
        },
    };
}
