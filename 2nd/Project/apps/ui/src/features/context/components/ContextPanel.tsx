/** Shows symbol provenance, selection/omission reasons, and bounded budget previews. */
import { Alert, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";

const omissionLabels: Record<string, string> = {
    budget_exceeded: "입력 한도 초과",
    depth_limit: "참조 범위 한도",
    duplicate: "중복 자료",
    too_large: "원문 크기 초과",
    stale_revision: "이전 버전",
    no_match: "일치하는 근거 없음",
    stale: "원본 변경됨",
    unauthorized: "접근 권한 없음",
    over_budget: "예산 부족",
};

export function ContextPanel(): React.JSX.Element {
    const candidate = fixtureAdapter.symbolSearch.candidates[0]!;
    const fragment = fixtureAdapter.symbolBundle.fragments[0]!;
    const omitted = fixtureAdapter.symbolBundle.omissions[0]!;
    const preview = fixtureAdapter.contextPreviews[0]!;
    const noMatch = fixtureAdapter.symbolNoMatch.no_match;

    return (
        <section className="feature-card" aria-labelledby="context-heading" data-testid="screen-context">
            <div className="feature-heading">
                <h2 id="context-heading">관련 코드 · 출처</h2>
                <StatusBadge label={`색인 버전 ${candidate.index_revision}`} tone="neutral" />
            </div>
            <article className="message-card">
                <h3>{candidate.primary.qualname}</h3>
                <p>
                    {candidate.primary.relative_path}:{candidate.primary.start_line}-{candidate.primary.end_line}
                </p>
                <p>
                    선택 이유: 관련도 {candidate.score.toFixed(2)} · 참조 깊이 {candidate.depth}
                </p>
                <p>
                    원문 출처: {fragment.provenance.relative_path} · sha256{" "}
                    {fragment.provenance.content_sha256.slice(0, 12)}…
                </p>
                <pre className="bounded-code">{boundedPreview(fragment.content, 160)}</pre>
            </article>
            <p>제외 이유: {omissionLabels[omitted.reason] ?? omitted.reason}</p>
            {noMatch ? (
                <Alert title="관련 코드 근거를 찾지 못했습니다" variant="info">
                    식별자나 파일 이름으로 다시 검색하세요.
                </Alert>
            ) : null}
            {preview.operation === "plan" ? (
                <div className="budget-box" data-testid="budget-preview">
                    <strong>전달 자료 예산</strong>
                    <p>
                        {preview.result.budget.used_tokens} / {preview.result.budget.budget_tokens} tokens ·{" "}
                        {preview.result.budget.count_mode === "provider_estimate"
                            ? "추정"
                            : preview.result.budget.count_mode}
                    </p>
                </div>
            ) : null}
            <Alert title="일부 자료가 전달 한도를 넘었습니다" variant="warning">
                {fixtureAdapter.pointerBudgetExceeded.error.message}
            </Alert>
            <Alert title="원본이 변경됐습니다" variant="warning">
                {fixtureAdapter.pointerSourceChanged.error.message}
            </Alert>
            <Alert title="자료 보관 기간이 끝났습니다" variant="warning">
                {fixtureAdapter.pointerExpired.error.message}
            </Alert>
            <details>
                <summary>검색·미리보기 상태 예시</summary>
                <p role="status">관련 코드와 전달 자료를 확인하는 중…</p>
                <Alert title="이전 미리보기를 사용할 수 없습니다" variant="error">
                    {fixtureAdapter.contextStale.error.message}
                </Alert>
                <p>일치 항목이 없으면 전체 파일을 대신 전달하지 않습니다.</p>
            </details>
        </section>
    );
}
