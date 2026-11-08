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
    const [intent, setIntent] = useState<ApprovalIntent | null>(null);
    const approvalId = state.snapshot?.pending_approvals[0]?.approval_id ?? null;

    return {
        intent,
        approvalId,
        open: setIntent,
        close: () => setIntent(null),
        confirm: () => {
            if (intent && approvalId) {
                void controller.decideApproval(approvalId, intent);
                setIntent(null);
            }
        },
    };
}
