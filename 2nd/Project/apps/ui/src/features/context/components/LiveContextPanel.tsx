import type {
    ExplicitContextRef,
    IndexStatusResponse,
    SelectedPointerContextRef,
    SessionId,
    WorkspaceId,
} from "@securecode/contracts";
import { useEffect } from "react";
import { Alert, Button, InputField, StatusBadge, TextAreaField } from "../../../components/index.js";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { useLiveContextWorkflow } from "../hooks/useLiveContextWorkflow.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";
import { countModeLabel, formatCitation } from "../../shared/model/provenanceLabels.js";

const omissionLabels: Record<string, string> = {
    duplicate: "이미 포함된 자료",
    in_history: "대화 이력에 이미 있음",
    large_fragment: "분할할 수 없는 원문이 한도 초과",
    no_match: "일치하는 근거 없음",
    over_budget: "컨텍스트 예산 초과",
    stale: "원본 또는 색인이 변경됨",
    unauthorized: "접근 권한 없음",
};

interface LiveContextPanelProps {
    api: ApiHttpClient;
    connected: boolean;
    workspaceId: WorkspaceId | null;
    sessionId: SessionId | null;
    index: IndexStatusResponse | null;
    pointerContextRef: SelectedPointerContextRef | null;
    onSourceChanged: () => void;
}

export function LiveContextPanel({
    api,
    connected,
    workspaceId,
    sessionId,
    index,
    pointerContextRef,
    onSourceChanged,
}: LiveContextPanelProps): React.JSX.Element {
    const workflow = useLiveContextWorkflow(api, workspaceId, sessionId, index, pointerContextRef);
    const searchable = Boolean(index?.searchable && index.index_status !== "stale");
    const koreanOnlyQuery = /[\uac00-\ud7af]/u.test(workflow.query) && !/[A-Za-z0-9_]/u.test(workflow.query);
    const sourceChanged = workflow.errorCode === "SOURCE_CHANGED";

    useEffect(() => {
        // The server marks the index stale once it sees the change; show that instead of the old "ready" status.
        if (sourceChanged) {
            onSourceChanged();
        }
    }, [sourceChanged, onSourceChanged]);

    return (
        <section className="feature-card" aria-labelledby="context-heading" data-testid="screen-context">
            <div className="feature-heading">
                <h2 id="context-heading">R0 원문 · 컨텍스트 예산</h2>
                <StatusBadge
                    label={
                        index ? `revision ${index.index_revision ?? "없음"} · ${index.index_status}` : "색인 확인 중"
                    }
                    tone={index?.index_status === "stale" || index?.index_status === "failed" ? "warning" : "neutral"}
                />
            </div>
            {!workspaceId ? <p role="status">R0 검색과 예산 미리보기를 위해 프로젝트를 등록하세요.</p> : null}
            {index?.index_status === "stale" ? (
                <Alert title="색인이 오래되었습니다" variant="warning">
                    프로젝트 파일이 바뀌었습니다. 색인을 다시 만든 뒤 검색하세요.
                </Alert>
            ) : null}
            <form
                className="stack-form"
                onSubmit={(event) => {
                    event.preventDefault();
                    void workflow.searchSymbols();
                }}
            >
                <InputField
                    id="r0-query"
                    label="심볼·파일 검색어"
                    value={workflow.query}
                    maxLength={2000}
                    disabled={!connected || !searchable || !workspaceId || workflow.busy !== null}
                    onChange={(event) => workflow.setQuery(event.currentTarget.value)}
                    data-testid="r0-query"
                />
                {koreanOnlyQuery ? (
                    <p role="status">
                        R0 TF-IDF는 한국어를 번역하지 않습니다. 함수·클래스 식별자나 파일명을 추가하세요.
                    </p>
                ) : null}
                <Button type="submit" disabled={!connected || !searchable || !workspaceId || workflow.busy !== null}>
                    {workflow.busy === "search" ? "R0 검색 중…" : "원문 심볼 검색"}
                </Button>
            </form>
            {workflow.search?.no_match ? (
                <Alert title="NO_MATCH · 일치하는 원문 심볼이 없습니다" variant="info">
                    식별자나 파일명으로 다시 검색하세요. 전체 파일을 대신 불러오지 않습니다.
                </Alert>
            ) : null}
            {workflow.search?.candidates.length ? (
                <div>
                    <h3>R0 후보 · TF-IDF 점수는 이 검색 응답 안에서만 비교 가능</h3>
                    <ul className="compact-list">
                        {workflow.search.candidates.map((candidate) => (
                            <li key={candidate.candidate_id}>
                                <label>
                                    <input
                                        type="radio"
                                        name="r0-candidate"
                                        checked={workflow.selectedCandidateId === candidate.candidate_id}
                                        onChange={() => workflow.selectCandidate(candidate.candidate_id)}
                                    />
                                    {candidate.primary.qualname} · {candidate.primary.relative_path}:
                                    {candidate.primary.start_line}-{candidate.primary.end_line} · score{" "}
                                    {candidate.score.toFixed(3)} · {candidate.estimated_tokens.token_count} tokens (
                                    {countModeLabel(candidate.estimated_tokens.count_mode)})
                                </label>
                            </li>
                        ))}
                    </ul>
                    {workflow.searchCursor ? (
                        <Button
                            type="button"
                            disabled={!connected || workflow.busy !== null}
                            onClick={() => void workflow.searchNext()}
                        >
                            다음 R0 검색 후보
                        </Button>
                    ) : null}
                    <Button
                        type="button"
                        disabled={!connected || workflow.busy !== null || !workflow.selectedCandidateId}
                        onClick={() => void workflow.readBundle()}
                    >
                        {workflow.busy === "bundle" ? "원문 묶음 읽는 중…" : "선택한 원문 묶음 읽기"}
                    </Button>
                </div>
            ) : null}
            {workflow.bundle ? (
                <div className="message-card" data-testid="r0-bundle">
                    <h3>Symbol Bundle · revision {workflow.bundle.index_revision}</h3>
                    <p>
                        {workflow.bundle.token_count.token_count} tokens ·{" "}
                        {countModeLabel(workflow.bundle.token_count.count_mode)}
                    </p>
                    {workflow.bundle.fragments.map((fragment) => (
                        <article key={fragment.symbol_id}>
                            <p>
                                {fragment.provenance.relative_path}:{fragment.start_line}-{fragment.end_line} · revision{" "}
                                {workflow.bundle?.index_revision} · sha256{" "}
                                {fragment.provenance.content_sha256.slice(0, 12)}…
                            </p>
                            <pre className="bounded-code">{boundedPreview(fragment.content, 4096)}</pre>
                        </article>
                    ))}
                    {workflow.bundle.omissions.map((omission) => (
                        <p key={`${omission.symbol_id}-${omission.reason}`}>
                            제외 {omission.symbol_id}: {omission.reason}
                        </p>
                    ))}
                    {workflow.bundle.unresolved_references.map((reference) => (
                        <p key={`${reference.from_symbol_id}-${reference.name}`}>
                            연결하지 못한 참조 {reference.name}: {reference.reason}
                        </p>
                    ))}
                </div>
            ) : null}
            <form
                className="stack-form"
                onSubmit={(event) => {
                    event.preventDefault();
                    void workflow.previewPlan();
                }}
            >
                <TextAreaField
                    id="context-prompt"
                    label="예산을 확인할 실제 질문"
                    value={workflow.prompt}
                    maxLength={4000}
                    disabled={!connected || !sessionId || !searchable || workflow.busy !== null}
                    onChange={(event) => workflow.setPrompt(event.currentTarget.value)}
                />
                <Button type="submit" disabled={!connected || !sessionId || !searchable || workflow.busy !== null}>
                    {workflow.busy === "plan" ? "예산 계산 중…" : "컨텍스트 미리보기"}
                </Button>
            </form>
            {!sessionId ? <p role="status">예산 계획에는 선택한 프로젝트의 세션이 필요합니다.</p> : null}
            {pointerContextRef ? (
                <p role="status">
                    명시 포함 요청: {pointerContextRef.kind} · revision {pointerContextRef.selection.revision} ·{" "}
                    {pointerContextRef.selection.range.type} 범위
                </p>
            ) : null}
            {workflow.plan ? (
                <div className="budget-box" data-testid="live-budget-preview">
                    <strong>호스트 컨텍스트 계획 · digest {workflow.plan.preview_digest.slice(0, 12)}…</strong>
                    <p>
                        실제 계수 {workflow.plan.budget.used_tokens} / {workflow.plan.budget.budget_tokens} tokens ·{" "}
                        {countModeLabel(workflow.plan.budget.count_mode)}
                    </p>
                    <ul className="compact-list">
                        {workflow.plan.selected.map((candidate) => (
                            <li key={candidate.candidate_id}>
                                선택: {candidate.origin} · 관련도 {candidate.score.toFixed(3)} · 예산 추정{" "}
                                {candidate.estimated_tokens} tokens
                            </li>
                        ))}
                    </ul>
                    {workflow.plan.fragments.map((fragment) => (
                        <article key={`${fragment.candidate_id}-${fragment.ref.kind}`}>
                            <p>
                                선택 이유: {inclusionLabel(fragment.inclusion)} · {fragment.token_count} tokens
                            </p>
                            <p>출처: {formatCitation(fragment.provenance)}</p>
                            <pre className="bounded-code">{boundedPreview(fragment.content, 4096)}</pre>
                        </article>
                    ))}
                    {workflow.plan.omitted.map((item, position) => (
                        <p key={`${item.candidate_id}-${item.reason}-${position}`}>
                            누락: {item.origin} {item.ref ? describeRef(item.ref) : item.candidate_id.slice(0, 17)} ·
                            이유 {omissionLabels[item.reason] ?? item.reason}
                        </p>
                    ))}
                    {workflow.plan.omissions_truncated ? <p>일부 누락 사유가 응답 상한으로 생략되었습니다.</p> : null}
                </div>
            ) : null}
            {workflow.error ? (
                <Alert title="컨텍스트 요청을 확인하세요" variant="error">
                    {workflow.error}
                </Alert>
            ) : null}
            {workflow.errorCode === "SOURCE_CHANGED" ? (
                <Alert title="SOURCE_CHANGED · 색인 또는 원본이 변경됨" variant="warning">
                    색인 상태를 다시 확인하고 Source 포인터는 갱신한 뒤 미리보기를 다시 요청하세요.
                </Alert>
            ) : null}
            {workflow.errorCode === "BUDGET_EXCEEDED" ? (
                <Alert title="BUDGET_EXCEEDED · 입력 예산 초과" variant="warning">
                    선택 범위나 질문을 줄인 다음 다시 계산하세요.
                </Alert>
            ) : null}
            {workflow.errorCode === "INDEX_NOT_READY" ? (
                <Alert title="색인이 아직 준비되지 않았습니다" variant="warning">
                    색인 상태가 searchable로 바뀐 뒤 다시 검색하세요.
                </Alert>
            ) : null}
            {!connected ? <p role="status">호스트 연결이 복구되면 API 요청을 다시 시도하세요.</p> : null}
        </section>
    );
}

function inclusionLabel(inclusion: string): string {
    switch (inclusion) {
        case "full":
            return "전체 포함";
        case "partial_budget":
            return "예산 때문에 일부만 포함";
        case "partial_size":
            return "조각 상한 때문에 일부만 포함";
        default:
            return inclusion;
    }
}

function describeRef(ref: ExplicitContextRef): string {
    return ref.kind === "symbol" ? `symbol revision ${ref.index_revision}` : `${ref.kind} ${ref.pointer}`;
}
