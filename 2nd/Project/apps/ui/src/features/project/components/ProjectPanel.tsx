/** Renders project registration and indexing states from workspace contracts. */
import { useState, type FormEvent } from "react";
import type { IndexDiagnostic, IndexState } from "@securecode/contracts";
import { Alert, Button, InputField, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { isProjectFormValid } from "../model/projectForm.js";

const stateLabels: Record<IndexState, string> = {
    not_indexed: "색인 없음",
    queued: "색인 대기 중",
    indexing: "색인 중",
    parsed: "분석 완료·검색 준비 중",
    partial: "일부 파일 제외",
    ready: "처리 완료",
    stale: "원본 변경·갱신 필요",
    failed: "색인 실패",
};

const diagnosticLabels: Record<IndexDiagnostic["reason_code"], string> = {
    syntax_error: "구문 오류",
    encoding_error: "문자 해석 실패",
    unsupported_language: "지원하지 않는 언어",
    too_large: "파일 크기 초과",
    excluded: "제외 규칙 적용",
    path_rejected: "허용되지 않은 경로",
};

export function ProjectPanel(): React.JSX.Element {
    const [displayName, setDisplayName] = useState("");
    const [rootPath, setRootPath] = useState("");
    const [submitted, setSubmitted] = useState(false);
    const [indexState, setIndexState] = useState(1);
    const index = fixtureAdapter.indexStates[indexState]!;
    const formValid = isProjectFormValid(displayName, rootPath);
    const diagnosticCount = index.diagnostics.length;

    function handleSubmit(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault();
        if (formValid) {
            setSubmitted(true);
        }
    }

    return (
        <section className="feature-card" aria-labelledby="project-heading" data-testid="screen-project">
            <div className="feature-heading">
                <h2 id="project-heading">프로젝트</h2>
                <StatusBadge label={fixtureAdapter.workspace.display_name} tone="neutral" />
            </div>
            <p>지원 색인 언어: {fixtureAdapter.workspace.supported_languages.join(", ")}</p>
            <form onSubmit={handleSubmit} className="stack-form">
                <InputField
                    id="project-display-name"
                    label="표시 이름"
                    value={displayName}
                    maxLength={120}
                    onChange={(event) => setDisplayName(event.currentTarget.value)}
                    data-testid="project-name"
                />
                <InputField
                    id="project-root-path"
                    label="로컬 프로젝트 경로"
                    value={rootPath}
                    maxLength={4096}
                    onChange={(event) => setRootPath(event.currentTarget.value)}
                    data-testid="project-path"
                />
                <Button type="submit" variant="primary" disabled={!formValid} data-testid="project-register">
                    프로젝트 등록 예시
                </Button>
            </form>
            {submitted ? <p role="status">입력 값이 유효합니다. 실제 등록 요청은 보내지 않았습니다.</p> : null}
            <div className="feature-heading">
                <h3>색인 상태</h3>
                <StatusBadge
                    label={
                        index.index_status === "ready" && !index.searchable
                            ? "검색할 코드 심볼 없음"
                            : stateLabels[index.index_status]
                    }
                    tone="warning"
                />
            </div>
            <div className="state-picker" role="group" aria-label="색인 계약 예시">
                {fixtureAdapter.indexStates.map((status, position) => (
                    <Button
                        key={`${status.index_status}-${status.index_revision ?? "none"}`}
                        type="button"
                        variant={indexState === position ? "primary" : "secondary"}
                        aria-pressed={indexState === position}
                        onClick={() => setIndexState(position)}
                        data-testid={`index-state-${status.index_status}`}
                    >
                        {status.index_status === "indexing"
                            ? "진행 중"
                            : status.index_status === "partial"
                              ? "부분 실패"
                              : status.index_status === "stale"
                                ? "원본 변경"
                                : status.searchable
                                  ? "완료"
                                  : "빈 색인"}
                    </Button>
                ))}
            </div>
            <p>
                발견 {index.counts.discovered} · 색인됨 {index.counts.indexed} · 제외 {index.counts.skipped} · 실패{" "}
                {index.counts.failed}
            </p>
            {diagnosticCount > 0 ? (
                <ul className="compact-list" aria-label="색인 제외 이유">
                    {index.diagnostics.map((diagnostic) => (
                        <li key={`${diagnostic.relative_path}-${diagnostic.reason_code}`}>
                            <code>{diagnostic.relative_path}</code> · {diagnosticLabels[diagnostic.reason_code]}
                        </li>
                    ))}
                </ul>
            ) : null}
            {index.index_status === "ready" && !index.searchable ? (
                <Alert title="검색할 코드 심볼이 없습니다" variant="info">
                    프로젝트에 지원 언어 파일이 있는지 확인하세요.
                </Alert>
            ) : null}
            {index.diagnostics_truncated ? <p role="status">진단 일부만 표시됩니다.</p> : null}
            {fixtureAdapter.workspaceListEmpty.items.length === 0 ? (
                <details>
                    <summary>프로젝트가 등록되지 않은 경우</summary>
                    <p>등록된 프로젝트가 없습니다. 프로젝트 경로를 입력해 등록할 수 있습니다.</p>
                </details>
            ) : null}
            <details>
                <summary>등록 오류와 원본 변경 예시</summary>
                <Alert title="프로젝트 경로를 확인하세요" variant="error">
                    {fixtureAdapter.workspacePathError.error.message}
                </Alert>
                {index.index_status === "stale" ? (
                    <Alert title="프로젝트 파일이 변경됐습니다" variant="warning">
                        새 색인을 만든 뒤 최신 버전으로 검색하세요.
                    </Alert>
                ) : null}
            </details>
        </section>
    );
}
