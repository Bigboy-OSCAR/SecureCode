/** Separates approval and rejection intents and keeps the fixture action explicit. */
import { useState } from "react";
import { Alert, Button, Modal, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";

type ApprovalIntent = "approve" | "reject";

export function ApprovalCard(): React.JSX.Element {
    const [intent, setIntent] = useState<ApprovalIntent | null>(null);
    const [confirmed, setConfirmed] = useState(false);
    const approval = fixtureAdapter.runs[0]!.pending_approvals[0]!;
    const modalTitle = intent === "approve" ? "실행을 승인하시겠습니까?" : "실행을 거절하시겠습니까?";

    function confirmIntent(): void {
        setConfirmed(true);
    }

    return (
        <section className="feature-card" aria-labelledby="approval-heading" data-testid="screen-approval">
            <div className="feature-heading">
                <h2 id="approval-heading">실행 승인</h2>
                <StatusBadge label="승인 대기" tone="warning" />
            </div>
            <p>{approval.review.summary}</p>
            <pre className="bounded-code">{boundedPreview(approval.review.content, 180)}</pre>
            {!approval.review.reviewable ? (
                <Alert title="검토 가능한 내용이 아닙니다" variant="error">
                    이 요청은 승인할 수 없습니다.
                </Alert>
            ) : (
                <div className="action-row">
                    <Button
                        type="button"
                        variant="primary"
                        onClick={() => {
                            setIntent("approve");
                            setConfirmed(false);
                        }}
                        data-testid="approval-approve"
                    >
                        승인 검토
                    </Button>
                    <Button
                        type="button"
                        onClick={() => {
                            setIntent("reject");
                            setConfirmed(false);
                        }}
                        data-testid="approval-reject"
                    >
                        거절 검토
                    </Button>
                </div>
            )}
            {confirmed ? (
                <Alert
                    title={intent === "approve" ? "승인 의도를 선택했습니다" : "거절 의도를 선택했습니다"}
                    variant="info"
                >
                    fixture 화면이며 서버에는 결정이 전송되지 않았습니다.
                </Alert>
            ) : null}
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
            <Modal open={intent !== null && !confirmed} title={modalTitle} onRequestClose={() => setIntent(null)}>
                <p>
                    {intent === "approve"
                        ? "검토한 변경 또는 명령 실행을 허용합니다."
                        : "이 요청을 거절하고 실행하지 않습니다."}
                </p>
                <div className="action-row">
                    <Button type="button" variant="primary" onClick={confirmIntent} data-testid="approval-confirm">
                        {intent === "approve" ? "승인 확정" : "거절 확정"}
                    </Button>
                    <Button type="button" onClick={() => setIntent(null)} data-testid="approval-back">
                        돌아가기
                    </Button>
                </div>
            </Modal>
        </section>
    );
}
