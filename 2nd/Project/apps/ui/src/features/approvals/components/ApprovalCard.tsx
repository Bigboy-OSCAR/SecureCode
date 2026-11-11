import { useEffect, useRef } from "react";
import type { ApprovalRequest } from "@securecode/contracts";
import { Alert, Button } from "../../../components/index.js";
import { DeskIcon } from "../../../components/DeskIcon.js";
import type { RunController } from "../../chat/model/runController.js";
import type { RunViewState } from "../../chat/model/runState.js";

export interface ApprovalCardProps {
    controller: RunController;
    state: RunViewState;
}

export function ApprovalCard({ controller, state }: ApprovalCardProps): React.JSX.Element | null {
    const approval = state.snapshot?.pending_approvals[0];
    if (
        !approval ||
        approval.status !== "pending" ||
        state.snapshot?.status !== "awaiting_approval" ||
        controller.isApprovalExpired(approval.approval_id)
    )
        return null;

    return <PendingApprovalCard key={approval.approval_id} controller={controller} state={state} approval={approval} />;
}

function PendingApprovalCard({
    controller,
    state,
    approval,
}: ApprovalCardProps & { approval: ApprovalRequest }): React.JSX.Element {
    const heading = useRef<HTMLHeadingElement>(null);
    const deciding = state.operation?.kind === "deciding_approval";
    const canApprove = controller.canDecideApproval(approval.approval_id, "approve");
    const canReject = controller.canDecideApproval(approval.approval_id, "reject");

    useEffect(() => {
        // Announce the request without putting a decision button under an in-flight Enter key.
        if (!document.querySelector("dialog[open]") && document.activeElement?.closest("#screen-chat")) {
            heading.current?.focus({ preventScroll: true });
        }
    }, []);

    const decide = async (decision: "approve" | "reject"): Promise<void> => {
        const focused = document.activeElement;
        if (await controller.decideApproval(approval.approval_id, decision)) {
            if (document.activeElement === focused || document.activeElement === document.body) {
                document.getElementById("question-input")?.focus({ preventScroll: true });
            }
        }
    };

    return (
        <section
            className="desk-approval-request"
            aria-labelledby="approval-heading"
            aria-busy={deciding}
            data-testid="screen-approval"
        >
            <div className="desk-approval-heading">
                <span className="desk-approval-icon">
                    <DeskIcon name="imgIconTerminal1" />
                </span>
                <div>
                    <p role="status">실행 권한 요청</p>
                    <h2 id="approval-heading" tabIndex={-1} ref={heading}>
                        {approval.review.kind === "file_change"
                            ? "이 파일 변경을 허용할까요?"
                            : "이 작업을 실행할까요?"}
                    </h2>
                </div>
            </div>
            <div className="desk-approval-content" data-testid="approval-meta">
                <p className="desk-approval-summary">{approval.review.summary}</p>
                <pre className="desk-approval-code">{approval.review.content}</pre>
                <details className="desk-approval-details">
                    <summary>요청 세부 정보</summary>
                    <dl className="approval-meta">
                        <dt>종류</dt>
                        <dd>{reviewKindLabel(approval.review.kind)}</dd>
                        <dt>도구</dt>
                        <dd>{approval.tool_name}</dd>
                        <dt>대상</dt>
                        <dd>{approval.review.target_paths?.join(", ") || "작업 공간 루트"}</dd>
                        <dt>만료</dt>
                        <dd>
                            <time dateTime={approval.expires_at}>
                                {new Date(approval.expires_at).toLocaleString("ko-KR")}
                            </time>
                        </dd>
                    </dl>
                </details>
                {approval.review.content_truncated || !approval.review.reviewable ? (
                    <Alert title="전체 작업 내용을 확인할 수 없어 허용할 수 없습니다" variant="error">
                        더 작은 작업을 요청하거나 이 요청을 거절하세요.
                    </Alert>
                ) : null}
                {state.connection === "disconnected" || state.connection === "recovering" ? (
                    <p role="status">연결을 확인하는 동안 결정을 기다립니다.</p>
                ) : null}
                {state.error ? (
                    <Alert title="요청 상태를 확인하세요" variant="warning">
                        {state.error}
                    </Alert>
                ) : null}
            </div>
            <div className="desk-approval-actions">
                <p role="status">{deciding ? "결정 결과 확인 중…" : "허용하기 전에는 실행하지 않습니다."}</p>
                <Button
                    type="button"
                    disabled={!canReject}
                    onClick={() => void decide("reject")}
                    data-testid="approval-reject"
                >
                    거절
                </Button>
                <Button
                    type="button"
                    variant="primary"
                    disabled={!canApprove}
                    onClick={() => void decide("approve")}
                    data-testid="approval-approve"
                >
                    허용
                </Button>
            </div>
        </section>
    );
}

function reviewKindLabel(kind: string): string {
    switch (kind) {
        case "command":
            return "명령 실행";
        case "file_change":
            return "파일 변경";
        default:
            return "기타 작업";
    }
}
