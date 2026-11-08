/** Renders the one-time local connection flow from public bootstrap fixtures. */
import { Alert, Button, InputField, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { useConnectionWorkflow } from "../hooks/useConnectionWorkflow.js";

export function ConnectionPanel(): React.JSX.Element {
    const workflow = useConnectionWorkflow();
    const showExpired = workflow.status === "expired";

    return (
        <section className="feature-card" aria-labelledby="connection-heading" data-testid="screen-connection">
            <div className="feature-heading">
                <h2 id="connection-heading">로컬 서비스 연결</h2>
                <StatusBadge label={workflow.status === "validated" ? "코드 형식 확인" : "연결 대기"} tone="neutral" />
            </div>
            <p>실행 창에 표시된 일회용 연결 코드를 입력하세요.</p>
            <form onSubmit={workflow.submit}>
                <InputField
                    id="connection-code"
                    label="연결 코드"
                    value={workflow.code}
                    maxLength={64}
                    pattern="(?:[A-Za-z0-9]|-){8,64}"
                    onChange={(event) => workflow.setCode(event.currentTarget.value)}
                    autoComplete="off"
                    data-testid="connection-code"
                />
                <Button type="submit" variant="primary" disabled={!workflow.canSubmit} data-testid="connect-submit">
                    연결
                </Button>
            </form>
            {workflow.status === "validated" ? (
                <Alert title="연결 예시를 확인했습니다" variant="info">
                    코드 형식만 확인했습니다. 실제 서비스에 연결하거나 코드를 저장하지 않았습니다.
                </Alert>
            ) : null}
            {showExpired ? (
                <Alert title="접속 코드가 만료되었습니다" variant="warning">
                    {fixtureAdapter.bootstrapExpired.error.message}
                    <Button type="button" onClick={workflow.dismissExpired} data-testid="dismiss-expired">
                        새 코드 입력
                    </Button>
                </Alert>
            ) : (
                <p role="status">새 연결 코드를 입력할 수 있습니다.</p>
            )}
            <p className="muted-copy">
                연결 성공 계약 예시: {fixtureAdapter.bootstrap.authenticated ? "인증됨" : "인증되지 않음"} · cookie 값은
                화면에 표시하지 않습니다.
            </p>
            <details>
                <summary>연결 상태 예시</summary>
                <p role="status">로컬 서비스 응답 확인 중…</p>
                <p>연결 코드가 비어 있으면 연결을 시작할 수 없습니다.</p>
                <p>{fixtureAdapter.healthPreauth.status === "ok" ? "서비스 응답 있음" : "서비스 확인 필요"}</p>
            </details>
        </section>
    );
}
