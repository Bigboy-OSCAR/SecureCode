/** Shows provider, budget, and protection readiness without exposing secrets. */
import { Alert, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";

export function SettingsPanel(): React.JSX.Element {
    const { provider, budget, protections } = fixtureAdapter.settings;
    const gateLabel =
        budget.final_request_gate === "enforced"
            ? "입력 한도 적용됨"
            : budget.final_request_gate === "unavailable"
              ? "입력 한도 확인 불가"
              : "입력 한도 검증 전";

    return (
        <section className="feature-card" aria-labelledby="settings-panel-heading" data-testid="screen-settings">
            <div className="feature-heading">
                <h2 id="settings-panel-heading">모델·예산 상태</h2>
                <StatusBadge label={provider.configured ? "모델 설정됨" : "모델 미설정"} tone="warning" />
            </div>
            <dl className="data-list">
                <div>
                    <dt>모델</dt>
                    <dd>{provider.model_id}</dd>
                </div>
                <div>
                    <dt>입력 한도</dt>
                    <dd>{budget.context_limit_tokens.toLocaleString()} tokens</dd>
                </div>
                <div>
                    <dt>출력 예약</dt>
                    <dd>{budget.max_output_tokens.toLocaleString()} tokens</dd>
                </div>
                <div>
                    <dt>보호 상태</dt>
                    <dd>{gateLabel}</dd>
                </div>
            </dl>
            {protections.map((protection) => (
                <p key={protection.name} className="status-line">
                    {protection.name === "runtime_pointer_hook" ? "큰 실행 결과 보관" : "실행 보호"}:{" "}
                    {protection.ready ? "사용 가능" : "확인 필요"}
                </p>
            ))}
            {!provider.configured ? (
                <Alert title="모델 설정이 필요합니다" variant="warning">
                    비밀 키는 이 화면에 입력하거나 표시하지 않습니다. 서버 설정을 확인하세요.
                </Alert>
            ) : null}
            <details>
                <summary>서비스 준비·예산 오류 상태 예시</summary>
                <p role="status">모델과 보호 기능 상태를 확인하는 중…</p>
                <Alert title="보호 기능을 사용할 수 없습니다" variant="error">
                    {fixtureAdapter.protectionUnavailable.error.message}
                </Alert>
                <Alert title="선택한 자료가 입력 예산을 넘었습니다" variant="warning">
                    {fixtureAdapter.pointerBudgetExceeded.error.message}
                </Alert>
            </details>
        </section>
    );
}
