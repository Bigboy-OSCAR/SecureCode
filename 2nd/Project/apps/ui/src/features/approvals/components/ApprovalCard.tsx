import { Alert, Button, Modal, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";
import { useApprovalActions } from "../hooks/useApprovalActions.js";
import type { RunController } from "../../chat/model/runController.js";
import type { RunViewState } from "../../chat/model/runState.js";

export interface ApprovalCardProps {
    controller: RunController;
    state: RunViewState;
}

export function ApprovalCard({ controller, state }: ApprovalCardProps): React.JSX.Element {
    const actions = useApprovalActions(controller, state);
    const approval = state.snapshot?.pending_approvals[0] ?? null;
    const expired = approval ? controller.isApprovalExpired(approval.approval_id) : false;
    const modalTitle = actions.intent === "approve" ? "실행을 승인하시겠습니까?" : "실행을 거절하시겠습니까?";
    const canReject = Boolean(approval && controller.canDecideApproval(approval.approval_id, "reject"));
    const canApprove = Boolean(approval && controller.canDecideApproval(approval.approval_id, "approve"));
    const decision = state.approvalDecision;

    return (
        <section className="feature-card" aria-labelledby="approval-heading" data-testid="screen-approval">
            <div className="feature-heading">
                <h2 id="approval-heading">실행 승인</h2>
                <StatusBadge label={approval ? "승인 대기" : "대기 승인 요청 없음"} tone="warning" />
            </div>
            {approval ? (
                <>
                    <p>{approval.review.summary}</p>
                    <pre className="bounded-code">{boundedPreview(approval.review.content, 180)}</pre>
                    {approval.review.content_truncated || !approval.review.reviewable ? (
                        <Alert title="전체 작업 내용을 확인할 수 없어 승인할 수 없습니다" variant="error">
                            더 작은 작업을 요청하거나 이 요청을 거절하세요.
                        </Alert>
                    ) : null}
                    {expired ? (
                        <Alert title="승인 기한이 지났습니다" variant="warning">
                            최신 실행 상태를 확인한 뒤 새 승인 요청을 기다리세요.
                        </Alert>
                    ) : null}
                    {state.connection === "disconnected" || state.connection === "recovering" ? (
                        <p role="status">연결을 확인하는 동안 승인 결정을 잠급니다.</p>
                    ) : null}
                    <p>승인 전에는 도구가 실행되지 않습니다.</p>
                    <div className="action-row">
                        <Button
                            type="button"
                            variant="primary"
                            disabled={!canApprove}
                            onClick={() => actions.open("approve")}
                            data-testid="approval-approve"
                        >
                            승인 검토
                        </Button>
                        <Button
                            type="button"
                            disabled={!canReject}
                            onClick={() => actions.open("reject")}
                            data-testid="approval-reject"
                        >
                            거절 검토
                        </Button>
                    </div>
                </>
            ) : (
                <p>실행을 시작하면 서버가 확인한 승인 요청이 여기에 표시됩니다.</p>
            )}
            {state.operation?.kind === "deciding_approval" ? <p role="status">결정 결과 확인 중…</p> : null}
            {approval && state.error ? (
                <Alert title="승인 상태를 확인하세요" variant="warning">
                    {state.error}
                </Alert>
            ) : null}
            {decision ? (
                <Alert title={`요청 ${approvalStatusLabel(decision.status)}`} variant="info">
                    승인 결정은 도구 실행 완료를 의미하지 않습니다. 실행 상태는 별도로 확인합니다.
                </Alert>
            ) : null}
            {state.snapshot?.approval_history?.map((item) => (
                <p key={item.approval_id} role="status">
                    {approvalStatusLabel(item.status)} · {item.tool_name}
                </p>
            ))}
            <details>
                <summary>빈 승인·오류·만료·거절 예시</summary>
                <p>
                    {fixtureAdapter.runs[1]!.pending_approvals.length === 0
                        ? "검토할 승인 요청이 없습니다."
                        : "승인 요청이 있습니다."}
                </p>
                <Alert title="승인 확인이 일치하지 않습니다" variant="error">
                    {fixtureAdapter.approvalDigestError.error.message}
                </Alert>
                <Alert title="승인 시간이 만료됐습니다" variant="warning">
                    {fixtureAdapter.approvalExpired.error.message}
                </Alert>
                <p>
                    {fixtureAdapter.approvalRejected.type === "run.approval_resolved" &&
                    fixtureAdapter.approvalRejected.payload.status === "rejected"
                        ? "요청된 작업이 거절된 예시입니다."
                        : "결정 결과를 확인할 수 없습니다."}
                </p>
            </details>
            <Modal open={actions.intent !== null} title={modalTitle} onRequestClose={actions.close}>
                <p>
                    {actions.intent === "approve"
                        ? "검토한 변경 또는 명령 실행을 허용합니다."
                        : "이 요청을 거절하고 실행하지 않습니다."}
                </p>
                <div className="action-row">
                    <Button
                        type="button"
                        variant="primary"
                        disabled={state.operation !== null}
                        onClick={actions.confirm}
                        data-testid="approval-confirm"
                    >
                        {actions.intent === "approve" ? "승인 확정" : "거절 확정"}
                    </Button>
                    <Button type="button" onClick={actions.close} data-testid="approval-back">
                        돌아가기
                    </Button>
                </div>
            </Modal>
        </section>
    );
}

function approvalStatusLabel(status: string): string {
    switch (status) {
        case "approved":
            return "승인됨";
        case "rejected":
            return "거절됨";
        case "expired":
            return "승인 기한 만료";
        case "cancelled":
            return "승인 요청 취소됨";
        case "pending":
            return "결정 대기";
        default:
            return "결정 상태 확인 필요";
    }
}
